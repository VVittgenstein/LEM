"""Freeze copies of the accepted input generators and fixed parameters."""
import shutil
from wcontext import *

def prepare():
    init();records=[]
    targets=[('pipline/mask_generator/common','mask_generator/common'),
      ('pipline/mask_generator/world_orogen','mask_generator/world_orogen'),
      ('pipline/mask_generator/world_orogen_gibbs','mask_generator/world_orogen_gibbs'),
      ('pipline/seafloor_generator','seafloor_generator'),('pipline/initial_bathymetry','initial_bathymetry')]
    for source,dest in targets:
        source=REPO/source;dest=VENDOR/dest
        for p in source.rglob('*'):
            if not p.is_file() or any(q in p.parts for q in ('__pycache__','bin','.git')):continue
            if p.suffix.lower() not in ('.py','.cs','.json','.md','.txt') and p.name not in ('LICENSE','COPYING'):continue
            q=dest/p.relative_to(source);q.parent.mkdir(parents=True,exist_ok=True)
            if not q.exists():shutil.copyfile(p,q)
            if sha(p)!=sha(q):raise ValueError(f'Existing frozen code differs: {q}')
            records.append({'original':str(p),'copy':str(q.relative_to(ROOT)),'sha256':sha(p)})
    for p,name in [(REPO/'output/seafloor_generator/mean_distance_v1/functions.json','sea_functions.json'),
         (REPO/'output/initial_bathymetry/fixed_profiles_v1/parameters.json','bathymetry_parameters.json'),
         (FIELD/'sources/viewer_colormaps.py','viewer_colormaps.py')]:
        q=INPUT/name
        if not q.exists():shutil.copyfile(p,q)
        if sha(p)!=sha(q):raise ValueError('Frozen input changed')
        records.append({'original':str(p),'copy':str(q.relative_to(ROOT)),'sha256':sha(p)})
    fields=[]
    for seed in range(1001,1009):
        for name in ('axis.json','field.npz','axis_field_parameters.json','metadata.json','pair_geometry.json'):
            p=FIELD/f'output/seed{seed}'/name;fields.append({'path':str(p),'sha256':sha(p)})
    for name in ('generate_fields.py','stat_models.py','models/DS5_model.json'):
        p=FIELD/name;fields.append({'path':str(p),'sha256':sha(p)})
    save(INPUT/'manifest.json',{'copied':records,'read_only_complete_fields':fields,'scope':'8 existing complete fields; rerun copied mask, sea-type and bathymetry components for 8 corresponding seeds'})
    print('Frozen',len(records),'code/parameter files and',len(fields),'field inputs',flush=True)

if __name__=='__main__':prepare()
