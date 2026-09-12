"""Evidence-backed batch summary; no shape labels enter the generator."""
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from common.io import read_json,write_json,write_csv
from common.render import font


def summarize(output):
    output=Path(output)
    rows=read_json(output/'diagnose_runs.json') if (output/'diagnose_runs.json').exists() else []
    rows=sorted(rows,key=lambda r:r['seed'])
    if rows:
        write_csv(output/'distribution.csv',[{k:v for k,v in r.items() if k not in ('directory','failed_metrics')} for r in rows])
        distribution=dict(n=len(rows),seeds=[r['seed'] for r in rows],partition_count=512,
            parameter_policy='same fixed settings; independently regenerated fields and sampling states',
            representative='chain 0 last recorded state; no appearance selection',
            median_fraction=float(np.median([r['fraction'] for r in rows])),
            area_range=[min(r['fraction'] for r in rows),max(r['fraction'] for r in rows)],
            area_below_50_count=sum(r['fraction']<.5 for r in rows),
            one_component_count=sum(r['components']==1 for r in rows),
            largest_at_least_90pct_count=sum(r['largest_fraction']>=.9 for r in rows),
            second_at_least_10pct_count=sum(r['second_fraction']>=.1 for r in rows),
            center_unselected_count=sum(not r['center_selected'] for r in rows),
            second_at_least_10pct_seeds=[r['seed'] for r in rows if r['second_fraction']>=.1],
            max_rhat=max(r['max_rhat'] for r in rows),minimum_bulk_ess=min(r['min_ess'] for r in rows),
            all_diagnostics_passed=all(not r['failed_metrics'] and not r['spatial_failed_count'] for r in rows),
            interpretation='90% and 10% are descriptive reporting cutoffs, not approved five-class boundaries or input constraints; 32 draws cannot establish rare-event probabilities')
        write_json(output/'distribution.json',distribution)
        tile,cols=250,4;rowh=288
        image=Image.new('RGB',(cols*tile+40,50+rowh*((len(rows)+cols-1)//cols)),'white');draw=ImageDraw.Draw(image)
        draw.text((15,10),'32 个额外种子 · 512 分区 · 固定参数',font=font(23),fill='black')
        for i,r in enumerate(rows):
            x,y=20+(i%cols)*tile,50+(i//cols)*rowh
            source=Image.open(Path(r['directory'])/'mask.png')
            image.paste(source.resize((250,250),Image.Resampling.NEAREST),(x,y))
            draw.text((x,y+251),f'{r["seed"]}  占比 {r["fraction"]:.1%}',font=font(15),fill='black')
            draw.text((x,y+270),f'最大 {r["largest_fraction"]:.1%}  第二 {r["second_fraction"]:.1%}',font=font(13),fill='black')
        image.save(output/'diagnostic_comparison.png')
    formal=read_json(output/'generate_runs.json')
    groups=[]
    for count in sorted({r['partition_count'] for r in formal}):
        subset=[r for r in formal if r['partition_count']==count]
        groups.append(dict(partition_count=count,n=len(subset),
            area_range=[min(r['fraction'] for r in subset),max(r['fraction'] for r in subset)],
            component_counts=[r['components'] for r in sorted(subset,key=lambda r:r['seed'])],
            center_unselected_count=sum(not r['center_selected'] for r in subset),
            minimum_bulk_ess=min(r['min_ess'] for r in subset),maximum_rhat=max(r['max_rhat'] for r in subset)))
    pilot_runs=read_json(output/'pilot_runs.json') if (output/'pilot_runs.json').exists() else []
    write_json(output/'batch_summary.json',dict(display_samples=len(formal),paired_base_seeds=len({r['seed'] for r in formal}),groups=groups,
        diagnostic_samples=len(rows),pilot_seeds=sorted({r['seed'] for r in pilot_runs}),
        pilot_variants=len({str(Path(r['directory']).parent) for r in pilot_runs}),parameter_record='selected_settings.json'))
    return groups


def seal_manifest(output):
    import sys,importlib.metadata
    from common.io import file_sha256,utc_now
    output=Path(output);root=Path(__file__).resolve().parents[1]
    source_files=list((root/'world_orogen_gibbs').rglob('*'))+[root/'run_world_orogen_gibbs.py',root/'run_world_orogen_gibbs.ps1']
    if (root/'compare_boundary_layers.py').exists():source_files.append(root/'compare_boundary_layers.py')
    source_files += [root/'world_orogen'/name for name in ('partitions.py','noise.py','render.py','LICENSE','THIRD_PARTY.md')]
    source_files += [p for p in (root/'common').glob('*.py')]
    sources=[p for p in source_files if p.is_file() and '__pycache__' not in p.parts]
    artifacts=[p for p in output.rglob('*') if p.is_file() and p.name!='manifest.json']
    commit='cc2662b4edd52231c4f65d8765f3ef12cd82d9b7'
    upstream=root.parents[1]/f'references/2026-09-10-platform-shape-methods/world-orogen/{commit}'
    upstream_names=('js/plates.js','js/coarse-plates.js','js/rng.js','js/simplex-noise.js','LICENSE')
    from .config import VERSION
    record=dict(created_utc=utc_now(),version=VERSION,python=sys.executable,
                upstream_commit=commit,upstream_files=[dict(path=str(upstream/name),sha256=file_sha256(upstream/name)) for name in upstream_names],
                libraries={name:importlib.metadata.version(name) for name in ('numpy','scipy','shapely','Pillow','matplotlib')},
                code_files=[dict(path=str(p),sha256=file_sha256(p)) for p in sorted(sources)],
                outputs=[dict(path=p.relative_to(output).as_posix(),bytes=p.stat().st_size,sha256=file_sha256(p)) for p in sorted(artifacts)])
    write_json(output/'manifest.json',record)
    for row in record['outputs']:
        if file_sha256(output/row['path'])!=row['sha256']:raise ValueError('manifest output changed')
    return dict(source_count=len(record['code_files']),output_count=len(artifacts),total_bytes=sum(r['bytes'] for r in record['outputs']))
