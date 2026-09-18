"""DS5 reference extraction, with explicit observational support and errors."""
import numpy as np
from scipy.spatial import cKDTree
from scipy.optimize import least_squares
from scipy import stats
from context import *
from inspect_sources import load_ds5, inspect
from stat_models import fit_positive, fit_correlation, normal_scores, survival

SETTINGS={'along_station_step_km':5.,'cross_step_km':2.,'smoothing_sigma_along_km':4.,
 'smoothing_sigma_cross_km':3.,'maximum_neighbor_gap_km':5.,'minimum_effective_cells':3.,
 'peak_search_cross_km':[-25.,25.],'minimum_peak_mm_yr':2.,'profile_minimum_length_km':12.,
 'far_tail_support_fraction':.25,'errors':'within-location scatter retained; reported errors do not shrink with rounded-coordinate multiplicity'}

def prepare():
    inspect(); a,xy,origin=load_ds5();info=jload(CHECKS/'DS5_quality.json')
    _,inverse=np.unique(a[:,:2],axis=0,return_inverse=True);n=inverse.max()+1
    weights=1/a[:,8]**2;den=np.bincount(inverse,weights=weights)
    xyg=np.column_stack([np.bincount(inverse,weights=weights*xy[:,j])/den for j in range(2)])
    ug=np.bincount(inverse,weights=weights*a[:,7])/den
    counts=np.bincount(inverse);err2=np.bincount(inverse,weights=a[:,8]**2)/counts
    err2+=np.bincount(inverse,weights=(a[:,7]-ug[inverse])**2)/counts
    basis=np.column_stack([info['along_unit'],info['cross_unit']]);sn=(xyg-info['center_local_km'])@basis
    ss=np.arange(np.ceil(sn[:,0].min()/5)*5,np.floor(sn[:,0].max()/5)*5+1,5.)
    nn=np.arange(-40,151,2.);S,N=np.meshgrid(ss,nn,indexing='ij');locations=np.column_stack([S.ravel(),N.ravel()])
    scale=np.array([4.,3.]);tree=cKDTree(sn/scale);near,indices=tree.query(locations/scale,k=64)
    actual=np.linalg.norm(sn[indices]-locations[:,None,:],axis=2)
    w=np.exp(-.5*near**2)/err2[indices];w[near>3]=0
    total=w.sum(axis=1);total=np.maximum(total,1e-30)
    mean=(w*ug[indices]).sum(axis=1)/total
    neff=total**2/np.maximum((w*w).sum(axis=1),1e-30)
    # This error is descriptive, not an independence-based confidence interval.
    error=np.sqrt((w*err2[indices]).sum(axis=1)/total)
    supported=(actual.min(axis=1)<=5)&(neff>=3)
    field=mean.reshape(S.shape);error=error.reshape(S.shape);valid=supported.reshape(S.shape)
    profiles=[];sides=[];profile_data=[];station_log=[]
    for i,s in enumerate(ss):
        candidate=valid[i]&(nn>=-25)&(nn<=25)
        if not candidate.any():continue
        ids=np.flatnonzero(candidate);k=int(ids[np.argmax(field[i,ids])]);peak=float(field[i,k]);npeak=float(nn[k])
        entry={'station_id':int(i),'s_km':float(s),'peak_cross_km':npeak,'peak_mm_yr':peak,'peak_error_mm_yr':float(error[i,k])}
        if peak<2 or k==ids[0] or k==ids[-1]:
            station_log.append({**entry,'status':'peak_not_interior_or_below_threshold'});continue
        local=[]
        for side,direction in [('nw',-1),('se',1)]:
            js=np.arange(k,len(nn)) if direction==1 else np.arange(k,-1,-1)
            # Follow native supported observations; stop after the first unsupported cell.
            stops=np.flatnonzero(~valid[i,js]);js=js[:stops[0]] if len(stops) else js
            if len(js)<7:continue
            d=abs(nn[js]-npeak);y=field[i,js]/peak;er=error[i,js]/peak
            if d[-1]<12 or np.min(y[1:])>.65:continue
            # Fit physical half-width and shape to actual supported, signed DS5 averages.
            fitted=[]
            for family in ('weibull','loglogistic','linear'):
                def fun(z):
                    h=np.exp(z[0]);p=np.exp(z[1]) if family!='linear' else 1
                    return (survival(d/h,family,p)-y)/np.maximum(er,.10)
                opt=least_squares(fun,[np.log(max(5,d[np.argmin(abs(y-.5))])),0.],
                   bounds=([np.log(1.),np.log(.3)],[np.log(400.),np.log(5.)]),loss='soft_l1')
                h=float(np.exp(opt.x[0]));p=float(np.exp(opt.x[1])) if family!='linear' else 1.
                prediction=survival(d/h,family,p);rmse=float(np.sqrt(np.mean((prediction-y)**2)))
                fitted.append(dict(family=family,halfwidth_km=h,shape=p,rmse=rmse,
                    weighted_sse=float(np.sum(fun(opt.x)**2)),success=bool(opt.success)))
            row={**entry,'side':side,'max_observed_distance_km':float(d[-1]),'minimum_observed_fraction':float(y.min()),
                 'observed_half_crossing':bool(np.any(y<=.5)),'n_supported':len(js),'fits':fitted}
            sides.append(row);profile_data.append({'station_id':int(i),'side':side,'distance':d.tolist(),'normalized_u':y.tolist(),'normalized_error':er.tolist()});local.append(row)
        if local:profiles.append(entry);station_log.append({**entry,'status':'used','usable_sides':len(local)})
    if len(profiles)<8 or len(sides)<12:raise RuntimeError('Insufficient supported profiles; inspect DS5 checks')
    mean_scores={fam:float(np.mean([next(f for f in row['fits'] if f['family']==fam)['rmse'] for row in sides])) for fam in ('weibull','loglogistic','linear')}
    # Linear is a comparison baseline. This family comparison is source-profile
    # reconstruction error; distribution models below use held spatial blocks.
    family=min(('weibull','loglogistic'),key=lambda k:mean_scores[k])
    for row in sides:row.update(next(f for f in row['fits'] if f['family']==family))
    u=np.array([p['peak_mm_yr'] for p in profiles]);s=np.array([p['s_km'] for p in profiles]);groups=np.floor((s-s.min())/20).astype(int)
    peak_model=fit_positive(u,groups);peak_corr=fit_correlation([(s,normal_scores(u))],60.,'km')
    shapes=np.array([r['shape'] for r in sides]);sg=np.array([int((r['s_km']-s.min())//20) for r in sides])
    shape_model=fit_positive(shapes,sg)
    sequences=[]
    for side in ('nw','se'):
        rr=[r for r in sides if r['side']==side]
        if len(rr)>4:sequences.append((np.array([r['s_km'] for r in rr]),normal_scores(np.array([r['shape'] for r in rr]))))
    shape_corr=fit_correlation(sequences,60.,'km')
    paired=[]
    for p in profiles:
        rr=[r for r in sides if r['station_id']==p['station_id'] and r['observed_half_crossing']]
        if len(rr)==2:
            w1=next(r['halfwidth_km'] for r in rr if r['side']=='nw');w2=next(r['halfwidth_km'] for r in rr if r['side']=='se')
            paired.append({**p,'nw_halfwidth_km':w1,'se_halfwidth_km':w2,'nw_fraction':w1/(w1+w2)})
    if len(paired)<5:raise RuntimeError('Insufficient paired half-width profiles')
    ratios=np.array([r['nw_fraction'] for r in paired]);aa,bb,_,_=stats.beta.fit(ratios,floc=0,fscale=1)
    ratio_corr=fit_correlation([(np.array([r['s_km'] for r in paired]),normal_scores(ratios))],60.,'km')
    flank_shapes={}
    for side in ('nw','se'):
        rr=[r for r in sides if r['side']==side]
        flank_shapes[side]=fit_positive(np.array([r['shape'] for r in rr]),np.array([int((r['s_km']-s.min())//20) for r in rr]))
    paired_shapes=[]
    for pr in paired:
        rr=[r for r in sides if r['station_id']==pr['station_id']]
        paired_shapes.append([pr['nw_fraction'],next(r['shape'] for r in rr if r['side']=='nw'),next(r['shape'] for r in rr if r['side']=='se')])
    joined=np.asarray(paired_shapes);joined=np.column_stack([normal_scores(joined[:,j]) for j in range(3)])
    joint_correlation=.9*np.corrcoef(joined.T)+.1*np.eye(3)
    joint_spatial=fit_correlation([(np.array([r['s_km'] for r in paired]),joined[:,j]) for j in range(3)],60.,'km')
    support_choices=[{'fraction':f,'covered_profiles':sum(r['minimum_observed_fraction']<=f for r in sides)} for f in (.05,.1,.15,.2,.25,.3)]
    cutoff=next(r['fraction'] for r in support_choices if r['covered_profiles']/len(sides)>=.8)
    SETTINGS['far_tail_support_fraction']=cutoff
    model={'source':'DS5 referenced vertical velocity','unit':'mm/yr','settings':SETTINGS,
      'support_convention':{'fraction':cutoff,'candidates':support_choices,'coverage_target':.8,
        'interpretation':'first candidate reached by at least 80% of supported half profiles; subtract this residual fraction and close to zero; a finite-domain convention, not observed zero uplift'},
      'stations':len(profiles),'side_profiles':len(sides),'paired_halfwidth_profiles':len(paired),
      'peak_distribution':peak_model,'peak_correlation':peak_corr,'decay_family':family,
      'decay_model_comparison_rmse':mean_scores,'shape_distribution':shape_model,'shape_correlation':shape_corr,
      'ratio_distribution':{'family':'beta','alpha':float(aa),'beta':float(bb),'training_values':ratios.tolist()},
      'ratio_correlation':ratio_corr,
      'flank_shape_distributions':flank_shapes,'ratio_shape_joint_correlation':joint_correlation.tolist(),
      'joint_correlation_regularization':'0.9 empirical normal-score correlation + 0.1 identity',
      'joint_shape_ratio_spatial_correlation':joint_spatial,
      'limitations':['one regional modern case; station sequences spatially dependent',
        'observed halves can be truncated; outer support is not measured by the data coverage edge',
        'half-height ratio converted to support-width ratio using each sampled compact decay profile',
        'nonlinear shape family fitted per side; exact zero obtained by an explicit observed-coverage tail closure',
        'profile averaging is an engineering noise treatment; negative raw DS5 values are retained',
        'positive-peak belt conditioned by selection; not distribution of all DS5 pixel velocities']}
    jsave(MODELS/'DS5_model.json',model);jsave(MODELS/'DS5_profiles.json',{'profiles':profiles,'sides':sides,'data':profile_data,'paired':paired,'station_log':station_log})
    csvsave(MODELS/'DS5_peak_sequence.csv',profiles);csvsave(MODELS/'DS5_paired_widths.csv',paired)
    csvsave(MODELS/'DS5_decay_fits.csv',[{k:v for k,v in r.items() if k!='fits'} for r in sides])
    np.savez_compressed(MODELS/'DS5_reference.npz',s=ss,n=nn,field=field,error=error,valid=valid,points_sn=sn,up=ug,error_group=np.sqrt(err2))
    plt=plotting();fig,ax=plt.subplots(2,2,figsize=(13,10));fig.subplots_adjust(hspace=.38,wspace=.27,top=.92,bottom=.08)
    z=np.where(valid,field,np.nan);im=ax[0,0].pcolormesh(ss,nn,z.T,cmap='turbo',vmin=0,vmax=10,shading='nearest');fig.colorbar(im,ax=ax[0,0],label='mm/yr')
    ax[0,0].plot(s,[p['peak_cross_km'] for p in profiles],c='black',lw=1.3);ax[0,0].set(title='DS5 误差加权局部平均及提取峰值',xlabel='沿带距离 km',ylabel='横带距离 km')
    ax[0,1].plot(s,u,'o-',c='#17679d',ms=4);ax[0,1].set(title=f'{len(profiles)}个支持剖面的峰值序列',xlabel='沿带距离 km',ylabel='峰值 mm/yr');ax[0,1].grid(alpha=.2)
    for row,dat in zip(sides,profile_data):
        d=np.array(dat['distance']);y=np.array(dat['normalized_u']);color='#17679d' if row['side']=='nw' else '#a86735'
        ax[1,0].plot(d/row['halfwidth_km'],y,c=color,alpha=.17,lw=.8)
        xx=np.linspace(0,min(4,d[-1]/row['halfwidth_km']),120);ax[1,1].plot(xx,survival(xx,family,row['shape']),c=color,alpha=.25)
    for a in ax[1]:a.set(xlim=(0,4),ylim=(-.3,1.2),xlabel='距离 / 拟合半高宽',ylabel='U / 剖面峰值');a.grid(alpha=.2)
    ax[1,0].set_title('观测剖面：蓝色 NW，棕色 SE');ax[1,1].set_title(f'拟合下降形态：{family}')
    fig.suptitle('DS5 统计提取与下降曲线拟合',fontsize=17);fig.savefig(CHECKS/'DS5_fitting.png',dpi=170);fig.savefig(CHECKS/'DS5_fitting.svg');plt.close(fig)
    print('DS5',len(profiles),len(sides),len(paired),family,mean_scores,flush=True)
    return model

if __name__=='__main__':prepare()
