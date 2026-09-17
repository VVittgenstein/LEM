"""Reproducible complete-axis generation entry point."""
import argparse,csv,json,os,time
from pathlib import Path
import numpy as np
from common import ROOT,MASTER_SEED,VERSION,write_json,write_csv,read_json,code_hashes,sha
from scale_model import fit,sample
from reference_statistics import extract
from axis_generator import generate,DESIGN

def save_axis(record,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);seed=record['seed']
    write_json(out/f'axis_seed{seed}.json',record)
    with (out/f'axis_seed{seed}_coordinates_km.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['edge_id','point_id','x_km','y_km','arc_along_edge_km'])
        for ei,pts in enumerate(record['edges']):
            p=np.array(pts);s=np.r_[0,np.linalg.norm(np.diff(p,axis=0),axis=1).cumsum()]
            for pi,(point,d) in enumerate(zip(p,s)):w.writerow([ei,pi,*[f'{v:.9f}' for v in point],f'{d:.9f}'])

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--start-seed',type=int,default=1001);ap.add_argument('--count',type=int,default=16)
    ap.add_argument('--out',default='output');ap.add_argument('--prepare-only',action='store_true');ap.add_argument('--refresh-models',action='store_true')
    args=ap.parse_args();out=(ROOT/args.out).resolve()
    if not out.is_relative_to(ROOT):raise ValueError('All outputs must remain inside this module')
    out.mkdir(parents=True,exist_ok=True)
    if args.refresh_models or not (ROOT/'tables/scale_model.json').exists():model=fit()
    else:model=read_json(ROOT/'tables/scale_model.json')
    if args.refresh_models or not (ROOT/'tables/geometry_reference.json').exists():reference=extract()
    else:reference=read_json(ROOT/'tables/geometry_reference.json')
    if args.prepare_only:return
    from render import draw_axis,plot_scale
    started=time.perf_counter();samples=[];source_hash=code_hashes()
    for seed in range(args.start_seed,args.start_seed+args.count):
        t=time.perf_counter();L,draw=sample(seed,model);print(f'Seed {seed}: G long side {L:.3f} km',flush=True)
        record=generate(seed,L,reference)
        record.update(version=VERSION,master_seed=MASTER_SEED,scale_draw=draw,scale_model_sha256=sha(ROOT/'tables/scale_model.json'),
          reference_statistics_sha256=sha(ROOT/'tables/geometry_reference.json'),code_hashes=source_hash)
        save_axis(record,out);draw_axis(record,out)
        row={'seed':seed,'target_long_km':L,'actual_long_km':record['actual_long_km'],'total_arc_length_km':record['total_arc_length_km'],
          'edges':len(record['edges']),**{k:record['graph'][k] for k in ['components','junctions','cycles']},
          'accepted_attempt':record['attempt'],'operation_layout_rejections':len(record['operation_rejections']),
          'fork_operations':record['structure_plan']['fork'],'rejoin_operations':record['structure_plan']['loop'],
          'split_operations':record['structure_plan']['split'],'seconds':time.perf_counter()-t,
          'json':f'axis_seed{seed}.json','png':f'axis_seed{seed}.png','svg':f'axis_seed{seed}.svg'}
        samples.append(row);write_csv(out/'samples.csv',samples);write_json(out/'run_progress.json',{'samples':samples})
        print(f"  Complete: edges={row['edges']} components={row['components']} junctions={row['junctions']} cycles={row['cycles']} attempt={row['accepted_attempt']} {row['seconds']:.2f}s",flush=True)
    run={'version':VERSION,'master_seed':MASTER_SEED,'start_seed':args.start_seed,'count':args.count,'sampling':'first admissible geometry per requested seed; fixed scale draw; no category quota or coverage feedback',
      'design':DESIGN,'samples':samples,'elapsed_seconds':time.perf_counter()-started,'code_hashes':source_hash,
      'model_sha256':sha(ROOT/'tables/scale_model.json'),'geometry_reference_sha256':sha(ROOT/'tables/geometry_reference.json')}
    write_json(out/'run_manifest.json',run);plot_scale(model,ROOT/'checks')
    print('Batch complete:',args.count,'axes;',run['elapsed_seconds'],'seconds',flush=True)

if __name__=='__main__':main()
