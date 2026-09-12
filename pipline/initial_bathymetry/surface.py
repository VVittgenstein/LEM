"""Continuous profiles and shallow/deep blending over immutable whole-region labels."""
import numpy as np
from scipy.ndimage import distance_transform_edt,gaussian_filter
from profiles import from_parameters,smoothstep
from roughness import make_noise


def base_surface(mask,types,params):
    sigma=params['surface']['distance_regularization_sigma_km']
    pad=int(np.ceil(4*sigma))+3
    # A halo permits an ordinary crop at the domain boundary. It introduces no
    # seaward wall and does not rescale the fixed profile to available space.
    m=np.pad(mask,pad,constant_values=False)
    nearest=distance_transform_edt(mask,return_distances=False,return_indices=True)
    extended_type=np.where(mask,types[tuple(nearest)],types)
    is_deep=np.pad(extended_type==2,pad,mode='edge')
    raw=np.maximum(0.,distance_transform_edt(~m)-.5)
    distance=gaussian_filter(raw,sigma,mode='nearest');distance[m]=0.
    ps,pd=from_parameters(params,'shallow'),from_parameters(params,'deep')
    zs,zd=ps.depth(distance),pd.depth(distance)
    gap=np.maximum(0.,zd-zs)
    width=np.maximum(params['surface']['lateral_min_width_km'],1.875*gap/pd.steep_m_per_km)
    if is_deep.any() and (~is_deep).any():
        signed=distance_transform_edt(is_deep)-distance_transform_edt(~is_deep)
        signed-=np.where(signed>0,.5,-.5)
        signed=gaussian_filter(signed,sigma,mode='nearest')
        weight=smoothstep(.5+signed/width)
    else:weight=np.full(m.shape,float(is_deep.all()))
    depth=(1-weight)*zs+weight*zd;depth[m]=params['platform_depth_m']
    crop=(slice(pad,-pad),slice(pad,-pad))
    # The noise amplitude is also C1 at the platform, where all surfaces share
    # the same shallow correlated field and its 2 m target.
    noise_weight=weight*smoothstep(distance/pd.width_km);noise_weight[m]=0.
    return dict(base_elevation=-depth[crop],distance_km=distance[crop],raw_distance_km=raw[crop],
          deep_weight=weight[crop],noise_deep_weight=noise_weight[crop],lateral_width_km=width[crop],
          shallow_profile=-zs[crop],deep_profile=-zd[crop])


def generate(sample,params):
    arrays=base_surface(sample['mask'],sample['sea_type'],params)
    noise,normalization,pure=make_noise(sample,params,arrays['noise_deep_weight'])
    arrays['roughness']=noise;arrays['elevation']=arrays['base_elevation']+noise
    arrays['target_local_std_m']=pure['target_local_std_m']
    # Keep the normalized source fields so the stated noise targets can be
    # audited independently of large-scale gradients and mixed boundaries.
    arrays['shallow_unit_noise']=pure['shallow_unit'];arrays['deep_unit_noise']=pure['deep_unit']
    if not np.isfinite(arrays['elevation']).all() or arrays['elevation'].max()>=0:
        raise ValueError('Initial surface must be finite and entirely submerged; no clipping or seed replacement is performed')
    return arrays,normalization
