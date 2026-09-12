import struct
import subprocess
from pathlib import Path
import numpy as np
from common.io import file_sha256,write_json

HERE=Path(__file__).resolve().parent
COMPILER=Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe')
METRICS=('energy','fraction','center_x_normalized','center_y_normalized','spread','perimeter','field',
         'components','largest_fraction','second_fraction','center_selected')


def build_kernel():
    source=HERE/'Sampler.cs'; executable=HERE/'bin/Sampler.exe'
    executable.parent.mkdir(exist_ok=True)
    marker=executable.with_suffix('.sha256')
    digest=file_sha256(source)
    if not executable.exists() or not marker.exists() or marker.read_text()!=digest:
        if not COMPILER.is_file(): raise RuntimeError('existing .NET compiler unavailable')
        run=subprocess.run([str(COMPILER),'/nologo','/optimize+','/target:exe',f'/out:{executable}',str(source)],
                           capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
        if run.returncode: raise RuntimeError(run.stdout+run.stderr)
        marker.write_text(digest)
    return executable


def run_sampler(directory,g,field,settings,seed,burn=2048,draws=1024,thin=4,chains=4,temperatures=(1.,2.,4.,8.)):
    if burn<0 or draws<4 or thin<1 or chains<2:
        raise ValueError('need nonnegative burn, at least 4 draws, positive stride and at least 2 chains')
    if not temperatures or temperatures[0]!=1. or any(not np.isfinite(t) or t<=0 for t in temperatures):
        raise ValueError('temperature ladder must start at target multiplier 1 and contain positive finite values')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    executable=HERE/'bin/Sampler.exe'
    if not executable.is_file():raise RuntimeError('build kernel before spawning workers')
    temperatures=np.asarray(temperatures)*settings.temperature
    src=directory/'sampler_input.bin'; dst=directory/'sampler_output.bin'
    with src.open('wb') as stream:
        stream.write(struct.pack('<7iIi',20260911,len(g.areas),chains,len(temperatures),burn,draws,thin,seed,g.center_id))
        stream.write(struct.pack('<8d',settings.center_weight,settings.spread_weight,settings.perimeter_weight,
                     settings.field_weight,settings.area_weight,settings.area_softness,settings.area_low,settings.area_high))
        stream.write(temperatures.astype('<f8').tobytes())
        for i in range(len(g.areas)):
            stream.write(struct.pack('<5dBi',g.areas[i],g.mx[i],g.my[i],g.m2[i],g.areas[i]*field[i],not g.forbidden[i],len(g.neighbors[i])))
            for j,length in g.neighbors[i]:stream.write(struct.pack('<id',j,length))
    process=subprocess.run([str(executable),str(src),str(dst)],capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
    (directory/'sampler.log').write_text(process.stdout+process.stderr,encoding='utf-8')
    if process.returncode:raise RuntimeError(process.stdout+process.stderr)
    with dst.open('rb') as stream:
        def read(fmt): return struct.unpack(fmt,stream.read(struct.calcsize(fmt)))
        magic,n,c,d=read('<4i')
        if (magic,n,c,d)!=(20260912,len(g.areas),chains,draws):raise ValueError('sampler output header')
        def state_record():
            sweep,=read('<i'); z=np.frombuffer(stream.read(n),np.uint8).astype(bool)
            values=np.asarray(read('<11d'))
            return sweep,z,values
        retained=[];stats=[];sweeps=[];histories=[];traces=[];exchange=[]
        for chain in range(chains):
            records=[state_record() for _ in range(draws)]
            sweeps.append([r[0] for r in records]);retained.append([r[1] for r in records]);stats.append([r[2] for r in records])
            count,=read('<i'); histories.append([state_record() for _ in range(count)])
            before=np.frombuffer(stream.read(n),np.uint8).astype(bool)
            count,=read('<i');updates=[]
            for _ in range(count):
                rid,old,new,p,u,e0,e1=read('<i??4d')
                updates.append(dict(region_id=rid+1,old=old,new=new,probability=p,uniform=u,
                                    energy_zero=e0 if np.isfinite(e0) else None,energy_one=e1))
            traces.append(dict(initial_state=before,updates=updates))
            count,=read('<i');exchange.append([read('<2q') for _ in range(count)])
        adds,removes=read('<2q')
        if stream.read(1):raise ValueError('unexpected sampler data')
    result=dict(states=np.asarray(retained),statistics=np.asarray(stats),sweeps=np.asarray(sweeps),
                histories=histories,traces=traces,exchange=exchange,adds=adds,removes=removes)
    np.savez_compressed(directory/'chain_samples.npz',states=result['states'],statistics=result['statistics'],sweeps=result['sweeps'])
    write_json(directory/'sampler_config.json',dict(seed=seed,burn_sweeps=burn,retained_per_chain=draws,thin=thin,
        chains=chains,temperatures=temperatures.tolist(),metric_columns=METRICS,adds=adds,removes=removes,
        swaps=[dict(proposals=[a for a,b in row],accepted=[b for a,b in row]) for row in exchange],
        representative='last retained state of chain 0, selected independently of appearance',
        kernel_sha256=file_sha256(executable),random_generator='PCG32; seed+chain*1000003 modulo 2^32',
        nonempty_only=True,center_locked=False,field_fixed_during_sampling=True))
    return result
