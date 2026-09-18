"""Simple correlated noise, with one fixed spatial scale per environment."""
import numpy as np
from scipy.ndimage import gaussian_filter,uniform_filter,binary_erosion
from scipy.optimize import minimize_scalar


def local_std(field,window=3):
    f=np.asarray(field,np.float64)
    # Remove a common offset before forming moments, including deep bathymetry.
    f=f-f.mean()
    mean=uniform_filter(f,window,mode='reflect')
    variance=uniform_filter(f*f,window,mode='reflect')-mean*mean
    return np.sqrt(np.maximum(variance,0.))


def fit_filter_scale(target_ratios,white):
    """Fit the short-scale 5/3 and 10/3 median-window-SD ratios.

The single Gaussian covariance family is an engineering simplification.
The fixed input white field makes this numerical calibration reproducible.
"""
    sl=(slice(64,-64),slice(64,-64));cache={}
    def evaluate(sigma):
        sigma=float(sigma)
        field=gaussian_filter(white,sigma,mode='wrap')
        values=[float(np.median(local_std(field,w)[sl])) for w in (3,5,10)]
        ratios=np.array(values[1:])/values[0]
        loss=float(np.mean(np.log(ratios/target_ratios)**2))
        cache[sigma]=(loss,ratios.tolist())
        return loss
    result=minimize_scalar(evaluate,bounds=(.5,12.),method='bounded',options={'xatol':.025})
    if not result.success:raise RuntimeError('Correlation-scale calibration failed')
    sigma=float(result.x);evaluate(sigma)
    return dict(gaussian_filter_sigma_km=sigma,covariance_efold_distance_km=2*sigma,
                reference_window_ratios=list(target_ratios),fitted_window_ratios=cache[sigma][1],
                log_ratio_mse=cache[sigma][0],fit_success=True,
                calibration_seed=39185,calibration_shape=list(white.shape),
                interpretation='3, 5, 10 km short-scale calibration; 25..100 km statistics retained for context, no full-spectrum fit claimed')


def unit_noise(seed,stream,sigma,normalization_mask):
    h,w=normalization_mask.shape
    pad=max(32,int(np.ceil(4*sigma))+8)
    rng=np.random.default_rng(np.random.SeedSequence([int(seed),175931,int(stream)]))
    field=gaussian_filter(rng.standard_normal((h+2*pad,w+2*pad)),sigma,mode='reflect')[pad:pad+h,pad:pad+w]
    field-=float(field[normalization_mask].mean())
    eligible=binary_erosion(normalization_mask,structure=np.ones((3,3)),border_value=0)
    if eligible.sum()<25:raise ValueError('Insufficient homogeneous cells to normalize correlated noise')
    scale=float(np.median(local_std(field,3)[eligible]))
    if scale<=0:raise ValueError('Degenerate random field')
    return field/scale,dict(normalization_cells=int(eligible.sum()),raw_median_3km_std=scale,
         gaussian_filter_sigma_km=sigma,stream=stream,
         rule='normalize each realization to the same specified local-SD target; no random parameter draws')


def make_noise(sample,params,noise_deep_weight):
    q=np.asarray(noise_deep_weight,float);typ=sample['sea_type'];seed=sample['seed']
    ns,info_s=unit_noise(seed,0,params['roughness']['shallow']['gaussian_filter_sigma_km'],typ!=2)
    if (typ==2).any():
        pure_deep=q>=.995
        usable=binary_erosion(pure_deep,structure=np.ones((3,3)),border_value=0).sum()
        norm_deep=pure_deep if usable>=25 else (typ==2)
        nd,info_d=unit_noise(seed,1,params['roughness']['deep']['gaussian_filter_sigma_km'],norm_deep)
        info_d['normalization_domain']='pure deep interior' if usable>=25 else 'assigned deep regions; no sufficient pure interior'
    else:nd=np.zeros_like(ns);info_d={'status':'no deep region in this sample'}
    target=2.+6.3*q
    # Independent normalized fields, with variance-preserving, smooth blending.
    noise=target*((1-q)*ns+q*nd)/np.sqrt((1-q)**2+q*q)
    return noise,dict(shallow=info_s,deep=info_d),dict(shallow_unit=ns,deep_unit=nd,target_local_std_m=target)
