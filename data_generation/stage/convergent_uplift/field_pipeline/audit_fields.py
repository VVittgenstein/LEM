"""Checks saved numbers, image geometry, provenance and deterministic replay."""
import argparse,hashlib,xml.etree.ElementTree as ET
from scipy.ndimage import map_coordinates
import numpy as np
from context import *
from generate_fields import axis_parameters,evaluate,mask_dimensions

def audit(out=OUT):
    out=Path(out);batch=jload(out/'batch.json');ds=jload(MODELS/'DS5_model.json');gm=jload(MODELS/'G_geometry_model.json')
    samples=[];peaks_input=[];peaks_final=[];shapes=[];references=[]
    for r in batch['samples']:
        seed=r['seed'];p=out/f'seed{seed}';a=jload(p/'axis.json');params=jload(p/'axis_field_parameters.json');meta=jload(p/'metadata.json');pair=jload(p/'pair_geometry.json')
        data=np.load(p/'field.npz');x=data['x_km'];y=data['y_km'];u=data['u_m_per_yr']*1000;mask=data['support']
        row={'seed':seed,'finite':bool(np.isfinite(u).all()),'nonnegative':bool((u>=0).all()),
            'zero_boundary':bool(not (u[0].any() or u[-1].any() or u[:,0].any() or u[:,-1].any())),
            'support_consistency':bool(np.array_equal(mask,u>0)),
            'A_B_same_limits':pair['A']['xlim']==pair['B']['xlim'] and pair['A']['ylim']==pair['B']['ylim'],
            'A_B_same_plot_pixels':pair['A']['axes_bbox_px']==pair['B']['axes_bbox_px'],
            'A_B_same_scale_bar':pair['A']['scale_bar_px']==pair['B']['scale_bar_px'],
            'A_B_same_transform':pair['A']['data_to_display']==pair['B']['data_to_display']}
        original=jload(AXIS_ROOT/f'output/axis_seed{seed}.json') if (AXIS_ROOT/f'output/axis_seed{seed}.json').exists() else None
        row['previous_axis_max_difference_km']=max(float(abs(np.array(e)-np.array(f)).max()) for e,f in zip(a['edges'],original['edges'])) if original else None
        paths=[]
        for kind in ('A','B'):
            root=ET.parse(p/f'{kind}.svg').getroot();found={}
            for group in root.iter():
                key=group.get('id','')
                if key.startswith(f'aux_seed{seed}_edge'):
                    found[key]=[z.get('d') for z in group.iter() if z.tag.endswith('path')]
            paths.append(found)
        row['SVG_identical_auxiliary_paths']=bool(paths[0] and paths[0]==paths[1] and len(paths[0])==len(a['edges']))
        # Fresh seed regeneration of continuous parameters and a common sparse grid.
        new,draw=axis_parameters(a,ds,gm);maxerr=0
        for e,saved in zip(new,params['edges']):
            for key in ('peak','shape_left','shape_right','half_ratio'):
                maxerr=max(maxerr,float(abs(e[key]-saved[key]).max()))
        row['seed_parameter_max_error']=maxerr
        xx=x[np.linspace(0,len(x)-1,min(101,len(x))).astype(int)];yy=y[np.linspace(0,len(y)-1,min(101,len(y))).astype(int)]
        regenerated=evaluate(new,xx,yy,meta['width_global_factor'],ds['decay_family'])
        actual=u[np.ix_(np.round(yy-y[0]).astype(int),np.round(xx-x[0]).astype(int))]
        row['replayed_grid_points']=int(actual.size);row['field_replay_max_error_mm_yr']=float(abs(regenerated-actual).max())
        dim=mask_dimensions(mask,x,y);row['width_relative_error']=dim['equivalent_width_km']/meta['parameters']['width_draw']['value_km']-1
        axlim=pair['view_extent_km'];b=dim['bbox'];row['full_support_inside_view']=bool(axlim[0]<=b[0] and axlim[1]>=b[1] and axlim[2]<=b[2] and axlim[3]>=b[3])
        row['saved_hashes_match']=sha(p/'field.npz')==meta['field_sha256'] and sha(p/'axis.json')==meta['axis_sha256']
        peak_rows=[]
        for e in params['edges']:
            xy=np.array(e['xy']);val=map_coordinates(u,np.array([xy[:,1]-y[0],xy[:,0]-x[0]]),order=1,mode='constant')
            peaks_input.extend(e['peak']);peaks_final.extend(val);shapes.extend(e['shape_left']);shapes.extend(e['shape_right'])
            peak_rows.append({'edge':e['edge_id'],'input_mean_mm_yr':float(np.mean(e['peak'])),'actual_mean_on_axis_mm_yr':float(val.mean()),
                'max_absolute_input_actual_difference_mm_yr':float(np.max(abs(val-e['peak'])))})
        jsave(p/'actual_axis_statistics.json',peak_rows)
        boolkeys=[k for k,v in row.items() if isinstance(v,bool)]
        row['passed']=all(row[k] for k in boolkeys) and maxerr<1e-12 and row['field_replay_max_error_mm_yr']<1e-10 and abs(row['width_relative_error'])<.06
        samples.append(row);print('audit',seed,row['passed'],'replay',row['field_replay_max_error_mm_yr'],flush=True)
    sourcecheck=[]
    for r in jload(RAW/'manifest.json')['files']:
        sourcecheck.append({'copy':r['copy'],'copy_hash':sha(ROOT/r['copy'])==r['sha256'],'original_hash':sha(r['original'])==r['sha256']})
    result={'passed':all(r['passed'] for r in samples) and all(r['copy_hash'] and r['original_hash'] for r in sourcecheck),
      'samples':samples,'sources':sourcecheck,'array_unit':'m/yr','plot_unit':'mm/yr',
      'DS5_used':True,'DS7_used':False,'reference_peak_range_mm_yr':[min(ds['peak_distribution']['training_values']),max(ds['peak_distribution']['training_values'])],
      'generated_input_peak_range_mm_yr':[float(min(peaks_input)),float(max(peaks_input))],
      'generated_actual_axis_range_mm_yr':[float(min(peaks_final)),float(max(peaks_final))],
      'interpretation':'Numerical/geometry/provenance checks; statistical fit quality and geological proxy assumptions are reported separately.'}
    jsave(CHECKS/'audit.json',result)
    plt=plotting();fig,ax=plt.subplots(1,3,figsize=(15,4.7));fig.subplots_adjust(wspace=.30,left=.07,right=.98,bottom=.22,top=.8)
    reference=np.asarray(ds['peak_distribution']['training_values']);
    for values,label,color in [(reference,'DS5提取峰值','#a86735'),(np.array(peaks_input),'生成沿线输入','#17679d'),(np.array(peaks_final),'实际场在辅助线上','#517a58')]:
        v=np.sort(values);ax[0].plot(v,np.arange(1,len(v)+1)/len(v),label=label,color=color)
    ax[0].legend(fontsize=8);ax[0].set(xlabel='mm/yr',ylabel='累计比例',title='峰值取值分布及场内回读')
    from stat_models import ppf,compact_profile
    rr=rng(91357,8);t=np.linspace(0,1,400)
    for side,color in [('nw','#17679d'),('se','#a86735')]:
        values=ppf(rr.random(12),ds['flank_shape_distributions'][side])
        for value in values:ax[1].plot(t,compact_profile(t,value,ds['decay_family'],ds['settings']['far_tail_support_fraction']),color=color,alpha=.35)
    ax[1].set(xlabel='距离 / 本侧生成宽度',ylabel='U / 起点U',title='新抽样的有限下降曲线')
    labels=[str(r['seed']) for r in samples];errors=[100*r['width_relative_error'] for r in samples]
    ax[2].bar(labels,errors,color='#17679d');ax[2].axhline(0,color='#4b5563',lw=.8);ax[2].set(ylabel='相对误差 %',title='实际等效宽度与G抽样目标');ax[2].tick_params(axis='x',labelrotation=45)
    for a in ax:a.grid(alpha=.15)
    fig.suptitle('生成结果与参考统计对照',fontsize=17)
    fig.text(.07,.055,'分布尾部允许模型外推；二维融合和参数向辅助线外延伸的改动由实际场回读显示。',fontsize=10)
    fig.savefig(CHECKS/'generation_statistics.png',dpi=170);fig.savefig(CHECKS/'generation_statistics.svg');plt.close(fig)
    if not result['passed']:raise RuntimeError('A saved field or image check failed; inspect checks/audit.json')
    return result

if __name__=='__main__':audit()
