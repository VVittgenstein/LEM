"""Independent readback, sampler diagnostics, complete-front audit and full seed replay."""
import argparse,csv,json,math,re,time
import xml.etree.ElementTree as ET
import numpy as np
from scipy import stats
from shapely.geometry import LineString,MultiLineString,Point
from common import ROOT,write_json,read_json,sha,code_hashes
from scale_model import sample,cdf,log_kde_logpdf
from axis_generator import generate,screen

def svg_comparison(file,record):
    tree=ET.parse(file);ns={'s':'http://www.w3.org/2000/svg'};seed=record['seed'];allpoints=np.vstack(record['edges'])
    lo=allpoints.min(axis=0);hi=allpoints.max(axis=0);extent=max(hi-lo);center=(lo+hi)/2
    xmin=center[0]-.59*extent;xmax=center[0]+.59*extent;ymin=center[1]-.59*extent;ymax=center[1]+.59*extent
    distances=[];counts=[]
    for ei,p in enumerate(record['edges']):
        group=tree.find(f'.//s:g[@id="axis_{seed}_edge_{ei}"]',ns);assert group is not None
        path=group.find('s:path',ns);cid=re.search(r'url\(#([^)]*)\)',path.attrib['clip-path']).group(1)
        rect=tree.find(f'.//s:clipPath[@id="{cid}"]/s:rect',ns);x0,y0,w,h=[float(rect.attrib[k]) for k in ('x','y','width','height')]
        tokens=re.findall(r'[A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?',path.attrib['d']);out=[]
        for i in range(0,len(tokens),3):
            assert tokens[i] in ('M','L');x,y=float(tokens[i+1]),float(tokens[i+2])
            out.append([xmin+(x-x0)/w*(xmax-xmin),ymax-(y-y0)/h*(ymax-ymin)])
        counts.append([len(p),len(out)]);distances.append(float(LineString(p).hausdorff_distance(LineString(out))))
    return {'max_distance_km':max(distances),'vertex_counts':counts,
      'passed':all(a==b for a,b in counts) and max(distances)<record['target_long_km']*1e-7}

def all_competitions(record):
    result=list(record['competition_sources'])
    for op in record['operations']:result+=op.get('curve_source',[])
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',default='output');ap.add_argument('--no-replay',action='store_true');args=ap.parse_args()
    out=(ROOT/args.out).resolve();assert out.is_relative_to(ROOT)
    run=read_json(out/'run_manifest.json');model=read_json(ROOT/'tables/scale_model.json');reference=read_json(ROOT/'tables/geometry_reference.json')
    original=read_json(ROOT/'sources/manifest.json');sources_ok=all(sha(ROOT/r['frozen_path'])==r['sha256'] for r in original)
    rows=[]
    for item in run['samples']:
        t=time.perf_counter();r=read_json(out/item['json']);seed=r['seed'];edges=[np.asarray(p) for p in r['edges']];nodes=np.array(r['graph']['nodes']);pairs=r['graph']['edge_nodes']
        # Direct source-coordinate calculations, separate from the generator's extent helper.
        rect=MultiLineString([p.tolist() for p in edges]).minimum_rotated_rectangle
        measured=float(max(np.linalg.norm(np.diff(np.array(rect.exterior.coords),axis=0),axis=1))) if rect.geom_type=='Polygon' else float(rect.length)
        saved_arc=float(sum(LineString(p).length for p in edges));degree=np.zeros(len(nodes),int);adj=[set() for _ in nodes];end_error=0.
        for p,(a,b) in zip(edges,pairs):
            degree[a]+=1;degree[b]+=1;adj[a].add(b);adj[b].add(a);end_error=max(end_error,float(np.linalg.norm(p[0]-nodes[a])),float(np.linalg.norm(p[-1]-nodes[b])))
        seen=set();comp=0
        for i in range(len(nodes)):
            if i in seen:continue
            comp+=1;seen.add(i);stack=[i]
            while stack:
                for j in adj[stack.pop()]:
                    if j not in seen:seen.add(j);stack.append(j)
        topology={'components':comp,'junctions':int(sum(degree==3)),'cycles':len(edges)-len(nodes)+comp}
        with (out/f'axis_seed{seed}_coordinates_km.csv').open(encoding='utf-8-sig') as f:tab=list(csv.DictReader(f))
        csv_error=0.;arc_error=0.;csv_rows_ok=True
        for ei,p in enumerate(edges):
            rr=[v for v in tab if int(v['edge_id'])==ei];csv_rows_ok &= len(rr)==len(p) and [int(v['point_id']) for v in rr]==list(range(len(p)))
            q=np.array([[float(v['x_km']),float(v['y_km'])] for v in rr]);s=np.r_[0,np.linalg.norm(np.diff(p,axis=0),axis=1).cumsum()]
            csv_error=max(csv_error,float(np.max(abs(q-p))));arc_error=max(arc_error,float(np.max(abs(np.array([float(v['arc_along_edge_km']) for v in rr])-s))))
        draw,_=sample(seed,model);svg=svg_comparison(out/item['svg'],r);replay_error=None;replay_topology=None
        if not args.no_replay:
            replay=generate(seed,draw,reference)
            if len(replay['edges'])==len(edges) and all(len(a)==len(b) for a,b in zip(replay['edges'],edges)):
                replay_error=max(float(np.max(abs(np.array(a)-b))) for a,b in zip(replay['edges'],edges))
            else:replay_error=1e100
            replay_topology=replay['graph']==r['graph']
        provenance=all_competitions(r)
        checked={'seed':seed,'target_long_km':draw,'measured_long_km':measured,'relative_scale_error':abs(measured-draw)/draw,
          'arc_error_km':abs(saved_arc-r['total_arc_length_km']),'csv_max_coordinate_error_km':csv_error,'csv_arc_error_km':arc_error,
          'max_node_endpoint_error_km':end_error,'topology':topology,'topology_matches':all(topology[k]==r['graph'][k] for k in topology),
          'complete_competition_sources':len(provenance),'all_sources_end_before_auxiliary_boundary':all(not v['active_front_touches_outer_boundary'] and v['free_tip_clearance_from_domain']>0 for v in provenance),
          'uncropped':r['complete_geometry'] and not r['cropped_to_500_km'],'geometric_rule_failures':screen(edges,reference),
          'svg':svg,'seed_replay_max_error_km':replay_error,'seed_replay_topology_matches':replay_topology,
          'code_hashes_match':r['code_hashes']==code_hashes(),'seconds':time.perf_counter()-t}
        checked['passed']=bool(checked['relative_scale_error']<1e-9 and checked['arc_error_km']<1e-7 and csv_rows_ok and csv_error<6e-10 and arc_error<6e-10 and end_error<1e-7 and checked['topology_matches'] and checked['all_sources_end_before_auxiliary_boundary'] and checked['uncropped'] and not checked['geometric_rule_failures'] and svg['passed'] and checked['code_hashes_match'] and (args.no_replay or replay_error==0 and replay_topology))
        rows.append(checked);write_json(ROOT/'checks/validation_progress.json',{'samples':rows});print('Validated',seed,checked['passed'],'replay error',replay_error,flush=True)
    # Validate the fitted sampler, independently of the 16-axis geometry rejection process.
    n=10000;draws=np.array([sample(i+300000,model)[0] for i in range(n)]);uniform=np.sort(cdf(draws,model))
    D=float(max(np.max(np.arange(1,n+1)/n-uniform),np.max(uniform-np.arange(n)/n)))
    zz=np.linspace(min(model.get('log_centers',np.log(model['training_values_km'])))-2,max(model.get('log_centers',np.log(model['training_values_km'])))+2,6000)
    integral=None
    if model['family']=='log_kde':
        xx=np.exp(zz);integral=float(np.trapezoid(np.exp(log_kde_logpdf(xx,np.array(model['log_centers']),model['bandwidth_log'])),xx))
    result={'passed':sources_ok and all(r['passed'] for r in rows) and D<.02 and (integral is None or abs(integral-1)<1e-5),
      'scope':'source integrity, saved coordinates, finite-completion records, geometry proxy/design rules, faithful SVG binding, fixed-seed replay and scale-sampler consistency',
      'scientific_limit':'G rectangle-to-axis scale mapping and fault-trace curvature transfer are explicit proxies. Branch/split laws remain documented design priors; this is not validation of a global geological distribution.',
      'source_hashes_passed':sources_ok,'samples':rows,'scale_sampler_check':{'n':n,'cdf_uniform_KS_D':D,'acceptance_threshold':.02,'pdf_integral':integral,'positive_draws':bool(np.all(draws>0))},
      'PNG_count':len(list(out.glob('axis_seed*.png'))),'SVG_count':len(list(out.glob('axis_seed*.svg'))),'seed_replay_performed':not args.no_replay}
    write_json(ROOT/'checks/validation.json',result);print('VALIDATION PASSED',result['passed'],'KS',D,flush=True)
    if not result['passed']:raise RuntimeError('Delivery validation failed')

if __name__=='__main__':main()
