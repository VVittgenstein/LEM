from __future__ import annotations
import argparse,json,sys,time
import numpy as np
from .common import ROOT,OUT,save,load,END,phase_records
from .fit import main as fit_models
from .forcing import create_episodes,build_basis,choose_window
from .faults import generate_faults
from .response import build_response

def timeline(episodes,faults):
    sys.path.insert(0,str(ROOT/'reporting'))
    from timeline import shared_timeline
    intervals=[];changes=[]
    for e in episodes:
        intervals.append(dict(id=e['id'],kind=e['kind'],start_year=e['start_Myr']*1e6,natural_end_year=e['natural_end_Myr']*1e6,phases=phase_records(e)))
    for f in faults:
        changes.append(dict(id=f['id'],kind='fault',time_year=f['birth_Myr']*1e6,detail='出现'))
        for k,part in enumerate(f['active_intervals']):
            a,b,d=[part[x]*1e6 for x in ['start_Myr','peak_Myr','natural_end_Myr']]
            intervals.append(dict(id=f"{f['id']}_{k}",kind='fault',start_year=a,natural_end_year=d,
                phases=[dict(name='增强',start_year=a,end_year=b),dict(name='减弱',start_year=b,end_year=d)]))
    return shared_timeline(intervals,changes,fractions=(0.,.33,.66,1.))

def generate(seed=1001,stage='all'):
    OUT.mkdir(parents=True,exist_ok=True);dest=OUT/f'seed{seed}';dest.mkdir(exist_ok=True)
    model=load(OUT/'models.json') if (OUT/'models.json').exists() else fit_models()
    if stage in ['all','forcing']:
        attempts=[]
        for length in [2000,3000,4000]:
            model['design_priors']['auxiliary_km']=length
            episodes=create_episodes(seed,model)
            basis=build_basis(episodes,model,seed)
            archive=dest/'forcing_attempts'/f'domain_{length}';archive.mkdir(parents=True,exist_ok=True)
            save(archive/'forcing.json',episodes);np.savez_compressed(archive/'basis.npz',basis_MPa=basis)
            try:window,mask,score=choose_window(basis,episodes,model,seed)
            except ValueError as error:
                attempts.append(dict(domain_km=length,accepted=False,reason=str(error)));continue
            attempts.append(dict(domain_km=length,accepted=True));break
        else:raise ValueError('No candidate auxiliary size provided a qualifying fixed window')
        save(dest/'forcing_attempts.json',dict(attempts=attempts,meaning='Different physical source layouts scaled with each auxiliary domain; not a fixed-load convergence experiment.'))
        save(dest/'model_run.json',model)
        save(dest/'forcing.json',episodes);save(dest/'window.json',window)
        np.savez_compressed(dest/'stress_basis.npz',basis_MPa=basis,eligible_centres=mask,worst_score=score)
        print('Fixed window',window['origin_km'],'score',window['selected_score'],flush=True)
        if stage=='forcing':return
    else:
        model=load(dest/'model_run.json');episodes=load(dest/'forcing.json');window=load(dest/'window.json');basis=np.load(dest/'stress_basis.npz')['basis_MPa']
    if stage in ['all','faults']:
        faults,data=generate_faults(seed,model,episodes,basis,window)
        save(dest/'faults.json',faults);np.savez_compressed(dest/'fault_history.npz',**data)
        save(dest/'timeline.json',timeline(episodes,faults))
        print('Generated faults',len(faults),flush=True)
        if stage=='faults':return
    else:faults=load(dest/'faults.json')
    if stage in ['all','response']:
        response=build_response(seed,model,faults,window) if faults else np.zeros((0,500,500,3),dtype=np.float32)
        np.save(dest/'response_basis.npy',response)
        print('Saved response',response.shape,flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--seed',type=int,default=1001);ap.add_argument('--stage',choices=['all','forcing','faults','response'],default='all');args=ap.parse_args()
    generate(args.seed,args.stage)

if __name__=='__main__':main()
