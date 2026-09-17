"""Derive curvature proxy statistics from frozen convergent-fault traces."""
import numpy as np
from pyproj import CRS,Transformer,Geod
from shapely.geometry import LineString
from common import ROOT,read_json,write_json,write_csv,sha
from geometry_metrics import features

def extract():
    src=ROOT/'sources/geology/GEM_pinned_faults.geojson';obj=read_json(src);geod=Geod(ellps='WGS84')
    rows=[];rejected={};kinds={'Reverse','Subduction_Thrust','Blind Thrust'}
    for index,f in enumerate(obj['features']):
        typ=f['properties'].get('slip_type')
        if typ not in kinds:continue
        g=f['geometry'];parts=[g['coordinates']] if g['type']=='LineString' else g['coordinates'] if g['type']=='MultiLineString' else []
        for partno,pts in enumerate(parts):
            p=np.asarray(pts,float)[:,:2]
            if len(p)<8:rejected['fewer_than_8_vertices']=rejected.get('fewer_than_8_vertices',0)+1;continue
            _,_,ds=geod.inv(p[:-1,0],p[:-1,1],p[1:,0],p[1:,1]);length=float(np.sum(ds)/1000)
            if length<100 or length>5000:rejected['outside_100_5000_km_analysis_window']=rejected.get('outside_100_5000_km_analysis_window',0)+1;continue
            lon=np.degrees(np.arctan2(np.sin(np.radians(p[:,0])).mean(),np.cos(np.radians(p[:,0])).mean()));lat=np.mean(p[:,1])
            crs=CRS.from_proj4(f'+proj=aeqd +lat_0={lat:.10f} +lon_0={lon:.10f} +datum=WGS84 +units=m')
            t=Transformer.from_crs('EPSG:4326',crs,always_xy=True);x,y=t.transform(p[:,0],p[:,1]);q=np.column_stack([x,y])/1000
            if not np.isfinite(q).all() or not LineString(q).is_simple:rejected['invalid_or_self_crossing_projection']=rejected.get('invalid_or_self_crossing_projection',0)+1;continue
            projected=float(LineString(q).length)
            if abs(projected/length-1)>.03:rejected['projection_length_error_over_3pct']=rejected.get('projection_length_error_over_3pct',0)+1;continue
            if np.linalg.norm(q[-1]-q[0])<.05*length:rejected['nearly_closed_trace']=rejected.get('nearly_closed_trace',0)+1;continue
            feat=features(q)
            rows.append({'source_feature_index':index,'part_index':partno,'catalog_id':f['properties'].get('catalog_id'),
              'name':f['properties'].get('name'),'slip_type':typ,'vertices':len(p),'geodesic_length_km':length,
              'projection_length_ratio':projected/length,**feat})
    metric_names=['sinuosity','net_turn_deg','absolute_turn_deg','turn_concentration','reversal_fraction','turn_03_p95_deg','turn_08_p95_deg','turn_20_p95_deg']
    summaries={}
    for typ in ['all',*sorted(kinds)]:
        rr=rows if typ=='all' else [r for r in rows if r['slip_type']==typ]
        if not rr:continue
        summaries[typ]={'n':len(rr)}
        for name in metric_names:
            values=np.array([r[name] for r in rr]);summaries[typ][name]={f'p{int(pct):02d}':float(np.percentile(values,pct)) for pct in [1,5,50,95,99]}
    result={'source_sha256':sha(src),'rows':len(rows),'rejected':rejected,'groups':summaries,
       'metric_definition':'Arc-normalized 257 points; heading smoothing sigma=2 samples; turn lags 3%, 8%, 20% of each trace length',
       'eligibility':'Reverse/Subduction_Thrust/Blind Thrust; at least 8 vertices; 100-5000 km; open simple trace; projected/geodesic length discrepancy <=3%',
       'grain':'source trace feature part; mapping subdivisions and repeated systems may share histories',
       'use':'geometric proxy for comparison and conservative turn/sinuosity screening, not a calibrated U-peak-axis distribution',
       'design_choices':'eligibility limits, measurement preprocessing and screening margins are engineering choices; all reported percentiles calculated from the retained source traces'}
    write_csv(ROOT/'tables/GEM_convergent_geometry.csv',rows);write_json(ROOT/'tables/geometry_reference.json',result)
    print('Convergent geometry proxy traces:',len(rows),'groups:',{k:v['n'] for k,v in summaries.items()},flush=True)
    print('Proxy p99:',{k:v['p99'] for k,v in summaries['all'].items() if isinstance(v,dict)},flush=True)
    return result

if __name__=='__main__':extract()
