"""Paired G extent/width probability and complete-polygon width profiles."""
import csv
from collections import defaultdict
import numpy as np
import shapefile
import shapely
from shapely.geometry import shape, LineString
from shapely.ops import transform
from pyproj import CRS, Transformer
from scipy import stats, special
from context import *
from stat_models import fit_positive, fit_correlation, normal_scores

def prepare():
    freeze()
    rows=list(csv.DictReader((RAW/'G_landmass_provinces.csv').open(encoding='utf-8-sig')))
    groups=defaultdict(list)
    for r in rows:
        if r['prov_type']=='orogenic belt' and r['in_primary_34']=='True':groups[r['province_key']].append(r)
    reader=shapefile.Reader(str(RAW/'global_gprv.shp'),encoding='utf-8')
    records=[];sequences=[];rel_values=[];rel_groups=[];caps=[];cap_groups=[]
    for gi,(key,rr) in enumerate(sorted(groups.items())):
        raw=shape(reader.shape(int(rr[0]['source_row'])-1).__geo_interface__)
        lon=float(rr[0]['longitude']);lat=float(rr[0]['latitude'])
        crs=CRS.from_proj4(f'+proj=laea +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m')
        tr=Transformer.from_crs(4326,crs,always_xy=True)
        def fn(x,y,z=None):
            a,b=tr.transform(x,y);return np.asarray(a)/1000,np.asarray(b)/1000
        poly=shapely.make_valid(transform(fn,shapely.segmentize(raw,.05)))
        rect=poly.minimum_rotated_rectangle;v=np.diff(np.asarray(rect.exterior.coords),axis=0);u=v[np.argmax(np.linalg.norm(v,axis=1))];u/=np.linalg.norm(u);n=np.array([-u[1],u[0]])
        center=np.asarray(poly.centroid.coords[0]);coords=(shapely.get_coordinates(poly)-center)@np.column_stack([u,n]);low=coords.min(axis=0);high=coords.max(axis=0)
        ss=np.linspace(low[0],high[0],131)[1:-1];ww=[]
        for s in ss:
            p1=center+s*u+(low[1]-10)*n;p2=center+s*u+(high[1]+10)*n
            ww.append(float(poly.intersection(LineString([p1,p2])).length))
        ww=np.asarray(ww);t=(ss-low[0])/(high[0]-low[0]);good=ww>1e-6
        equivalent=float(np.median([float(r['full_mean_width_km']) for r in rr]));L=float(np.median([float(r['full_long_km']) for r in rr]))
        relative=ww[good]/np.mean(ww[good]);sequences.append((t[good],normal_scores(relative)))
        # Identical normalized station spacing gives near-equal source contribution.
        rel_values.extend(relative);rel_groups.extend([gi]*sum(good))
        middle=ww[(t>.25)&(t<.75)&good];reference=float(np.median(middle))
        above=np.flatnonzero(ww>=.5*reference)
        ends=[]
        if len(above):
            ends=[max(.001,float(ss[above[0]]-low[0]))/equivalent,
                  max(.001,float(high[0]-ss[above[-1]]))/equivalent]
            caps.extend(ends);cap_groups.extend([gi,gi])
        records.append(dict(province_key=key,name=rr[0]['prov_name'],long_km=L,equivalent_width_km=equivalent,
           source_row=int(rr[0]['source_row']),profile_position_fraction=t.tolist(),width_km=ww.tolist(),
           relative_width=relative.tolist(),zero_slice_count=int((~good).sum()),cap_ratio=ends,
           projected_area_km2=float(poly.area),projection_long_km=float(high[0]-low[0]),projection_short_km=float(high[1]-low[1])))
    x=np.log([[r['long_km'],r['equivalent_width_km']] for r in records]);cov=np.cov(x.T);cov+=np.eye(2)*1e-5
    scores=[]
    for h in np.geomspace(.25,1.6,32):
        ll=[]
        for i in range(len(x)):
            c=np.delete(x,i,axis=0);ll.append(float(special.logsumexp(stats.multivariate_normal.logpdf(x[i]-c,mean=[0,0],cov=cov*h*h))-np.log(len(c))))
        scores.append({'bandwidth':float(h),'loo_joint_log_density':float(np.mean(ll))})
    chosen=max(scores,key=lambda q:q['loo_joint_log_density'])
    width_model={'family':'bivariate_log_kde_conditional','centers':x.tolist(),'covariance':cov.tolist(),**chosen,
       'candidate_scores':scores,'unit':'km','n_sources':len(records),
       'definition':'G complete projected area divided by complete minimum-rectangle long side',
       'conditioning':'previously generated auxiliary-axis extent used as G long-side proxy'}
    # Source-weighted empirical histogram is diagnostic; positive law is fitted continuously.
    relmodel=fit_positive(np.array(rel_values),np.array(rel_groups))
    corr=fit_correlation(sequences,.45,'fraction of G complete long side')
    capmodel=fit_positive(np.array(caps),np.array(cap_groups))
    model={'width_scale':width_model,'relative_width_distribution':relmodel,'relative_width_correlation':corr,
      'cap_ratio_distribution':capmodel,'cap_definition':'distance from complete geometric tip to first half-central-width cross-section, divided by G equivalent width',
      'assumptions':['G total widths are geometric province proxies, not directly observed contemporaneous U-support widths',
       'G minimum-rectangle projection axis used to measure total slice width; no claim that this is a U ridge',
       'tip-to-half-width distances transfer to auxiliary-line endpoint extension as a geometric design mapping',
       'generated area-equivalent width is checked separately after overlaps and caps']}
    jsave(MODELS/'G_geometry_model.json',model);jsave(MODELS/'G_width_profiles.json',records)
    csvsave(MODELS/'G_paired_dimensions.csv',[{k:v for k,v in r.items() if k in ('province_key','name','source_row','long_km','equivalent_width_km','zero_slice_count')} for r in records])
    plot_diagnostics(records,model)
    print('G',len(records),'width bandwidth',chosen['bandwidth'],'relative correlation',corr['length'],'cap median',np.median(caps),flush=True)
    return model

def plot_diagnostics(records,model):
    x=np.log([[r['long_km'],r['equivalent_width_km']] for r in records]);corr=model['relative_width_correlation']
    plt=plotting();fig,ax=plt.subplots(1,3,figsize=(15,4.8));fig.subplots_adjust(left=.065,right=.97,wspace=.32,bottom=.2,top=.82)
    ax[0].scatter(np.exp(x[:,0]),np.exp(x[:,1]),c='#17679d');ax[0].set(xscale='log',xlabel='完整长边 km',ylabel='等效宽度 km',title='15个源分区的成对尺度')
    from matplotlib.ticker import FixedLocator,FixedFormatter,NullFormatter
    ax[0].xaxis.set_major_locator(FixedLocator([300,500,1000,2000,3000]));ax[0].xaxis.set_major_formatter(FixedFormatter(['300','500','1000','2000','3000']));ax[0].xaxis.set_minor_formatter(NullFormatter())
    for r in records:ax[1].plot(r['profile_position_fraction'],np.array(r['width_km'])/np.mean(np.array(r['width_km'])[np.array(r['width_km'])>0]),alpha=.5)
    ax[1].set(xlabel='沿矩形长轴的位置比例',ylabel='截面总宽度 / 本分区平均',title='完整轮廓的宽度变化')
    ax[2].plot(corr['lags'],corr['variogram'],'o',label='逐源等权统计');ax[2].plot(corr['lags'],corr['model_variogram'],label='相关模型');ax[2].legend();ax[2].set(xlabel='距离 / 完整长边',ylabel='标准化半方差',title='宽度变化的空间统计')
    for a in ax:a.grid(alpha=.15)
    fig.suptitle('G完整几何统计及代理映射',fontsize=17);fig.savefig(CHECKS/'G_fitting.png',dpi=170);fig.savefig(CHECKS/'G_fitting.svg');plt.close(fig)
if __name__=='__main__':
    import sys
    if '--render-only' in sys.argv:plot_diagnostics(jload(MODELS/'G_width_profiles.json'),jload(MODELS/'G_geometry_model.json'))
    else:prepare()
