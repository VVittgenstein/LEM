"""Compare generated Gibbs batches without changing any sampled masks."""
from dataclasses import asdict
from pathlib import Path
import argparse
if __name__=='__main__':
    from common.runtime import configure_process_tree
    configure_process_tree(1)
import numpy as np
from PIL import Image,ImageDraw
from common.io import read_json,write_json,write_csv,file_sha256
from common.render import font
from .config import Settings,OUTPUT
from .geometry import geometry


def compare(layers=(4,5)):
    root=OUTPUT.parent
    target=root/('world_orogen_gibbs_layers_'+'_'.join(map(str,layers))+'_comparison')
    target.mkdir(parents=True,exist_ok=True)
    roots={k:root/f'world_orogen_gibbs_layers_{k}' for k in layers}
    samples={k:read_json(folder/'samples.json') for k,folder in roots.items()}
    keys=[{(s['partition_count'],s['seed']) for s in values} for values in samples.values()]
    if any(key!=keys[0] for key in keys[1:]):raise ValueError('batch sample sets differ')
    counts=sorted({k[0] for k in keys[0]});seeds=sorted({k[1] for k in keys[0]})
    records=[];lookup={};conditions=[];source_files=[]
    for layer,values in samples.items():
        for sample in values:
            count,seed=sample['partition_count'],sample['seed']
            folder=roots[layer]/sample['relative_path']
            config=read_json(folder/'config.json');settings=Settings.from_record(config)
            if settings.boundary_layers!=layer:raise ValueError('boundary-layer metadata mismatch')
            labels=np.load(folder/'partitions.npy');mask=np.load(folder/'mask.npy')
            g=geometry(labels,layer);z=np.zeros(len(g.areas),bool)
            z[np.unique(labels[mask])-1]=True
            assert not z[g.forbidden].any()
            edges=g.edges;coast=z[edges[:,0]]!=z[edges[:,1]]
            adjacent=(z[edges[:,0]] & g.forbidden[edges[:,1]]) | (z[edges[:,1]] & g.forbidden[edges[:,0]])
            old=root/'world_orogen_gibbs_layers_3'/sample['relative_path']
            before=read_json(old/'config.json');a=asdict(settings);b=asdict(Settings.from_record(before))
            a.pop('boundary_layers');b.pop('boundary_layers')
            current_run=read_json(folder/'sampler_config.json');previous_run=read_json(old/'sampler_config.json')
            checks=dict(parameters_except_layers_match=a==b,
                partition_arrays_match=config['partition_array_sha256']==before['partition_array_sha256'],
                base_fields_match=config['base_fields_array_sha256']==before['base_fields_array_sha256'],
                sampler_schedule_matches=all(current_run[k]==previous_run[k] for k in
                    ('seed','burn_sweeps','retained_per_chain','thin','chains','temperatures','kernel_sha256')))
            if not all(checks.values()):raise ValueError(f'comparison conditions differ: {folder}: {checks}')
            conditions.append(dict(layer=layer,partition_count=count,seed=seed,checks=checks))
            for name in ('mask.npy','mask.png','config.json','sampler_config.json'):
                p=folder/name;source_files.append(dict(path=str(p),sha256=file_sha256(p)))
            m=sample['metrics']
            available_cells=int(np.count_nonzero((~g.forbidden)[labels-1]))
            row=dict(layer=layer,partition_count=count,seed=seed,actual_fraction=float(mask.mean()),
                available_fraction=available_cells/mask.size,
                occupied_available_fraction=int(mask.sum())/available_cells,
                boundary_contact_fraction=float(g.lengths[adjacent].sum()/g.lengths[coast].sum()),
                components=m['components_4'],largest_fraction=m['largest_component_fraction'],
                minimum_edge_distance_km=m['nearest_domain_edge_km'],
                source_dir=str(folder),sampling_diagnostics_passed=sample['diagnostics']['all_passed'])
            records.append(row);lookup[layer,count,seed]=row

    def board(rows,kind):
        canvas=Image.new('RGB',(48+524*len(layers)-24,95+570*len(rows)),'white');draw=ImageDraw.Draw(canvas)
        caption=f'种子 {kind[1]}' if kind[0]=='seed' else f'{kind[1]} 个分区'
        draw.text((24,12),caption+' · 不同外围禁选层数',font=font(26),fill='black')
        draw.text((24,51),'相同分区、基础随机场与评分参数；图中为实际抽样台地',font=font(18),fill='black')
        for index,(count,seed) in enumerate(rows):
            for col,layer in enumerate(layers):
                r=lookup[layer,count,seed];x,y=24+524*col,95+570*index
                draw.text((x,y),f'{count} 分区 · 禁 {layer} 层 · 种子 {seed}',font=font(21),fill='black')
                with Image.open(Path(r['source_dir'])/'mask.png') as image:canvas.paste(image,(x,y+34))
                draw.text((x,y+541),f'台地 {r["actual_fraction"]:.2%} · 可选区占用 {r["occupied_available_fraction"]:.1%} · 连通 {r["components"]}',font=font(16),fill='black')
        filename=f'{kind[0]}{kind[1]}.png';canvas.save(target/filename)
        for index,(count,seed) in enumerate(rows):
            for col,layer in enumerate(layers):
                x,y=24+524*col,95+570*index+34
                with Image.open(Path(lookup[layer,count,seed]['source_dir'])/'mask.png') as image:
                    assert np.array_equal(np.asarray(canvas.crop((x,y,x+500,y+500))),np.asarray(image))
        return filename

    seed_images={seed:board([(count,seed) for count in counts],('seed',seed)) for seed in seeds}
    count_images={count:board([(count,seed) for seed in seeds],('partitions_',count)) for count in counts}
    groups=[]
    for count in counts:
        for layer in layers:
            group=[r for r in records if r['partition_count']==count and r['layer']==layer]
            groups.append(dict(partition_count=count,layer=layer,n=len(group),
                actual_fraction_range=[min(r['actual_fraction'] for r in group),max(r['actual_fraction'] for r in group)],
                occupied_available_range=[min(r['occupied_available_fraction'] for r in group),max(r['occupied_available_fraction'] for r in group)],
                component_counts=[r['components'] for r in sorted(group,key=lambda r:r['seed'])]))
    write_csv(target/'samples.csv',records)
    write_json(target/'summary.json',dict(layers=layers,counts=counts,seeds=seeds,samples=len(records),groups=groups,
        records=records,conditions=conditions,source_files=source_files,
        all_pairing_checks_passed=True,comparison_tiles_match=True,
        note='occupied_available_fraction measures selected area / eligible area; it is not the area fraction of the full domain'))
    table=''.join(f'<tr><td>{g["partition_count"]}</td><td>{g["layer"]}</td><td>{g["actual_fraction_range"][0]:.2%} 至 {g["actual_fraction_range"][1]:.2%}</td><td>{g["occupied_available_range"][0]:.1%} 至 {g["occupied_available_range"][1]:.1%}</td></tr>' for g in groups)
    links=' · '.join(f'<a href="../{folder.name}/report.html">禁{layer}层全部四阶段图</a>' for layer,folder in roots.items())
    figures=''.join(f'<h2>种子 {seed}</h2><details'+(' open' if seed==seeds[0] else '')+f'><summary>三种分区数量的配对结果</summary><a href="{filename}"><img src="{filename}" loading="lazy"></a></details>' for seed,filename in seed_images.items())
    count_links=' · '.join(f'<a href="{filename}">{count}分区的六组配对</a>' for count,filename in count_images.items())
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>外围4层与5层批次对照</title><style>body{font:16px/1.65 system-ui,"Microsoft YaHei";background:#f1f4f7;color:#1c2c40;margin:24px}main{max-width:1150px;margin:auto}img{max-width:100%;image-rendering:pixelated}a{color:#155e92}table{border-collapse:collapse;background:white}th,td{padding:8px 15px;border:1px solid #cad3dd}summary{cursor:pointer}</style><main><h1>外围禁4层与5层：36份实际台地</h1><p>两批仅改变禁选层数。分区图、随机场、评分参数和抽样安排与3层批次逐份核对一致。没有按外观筛选样本。</p><p>__LINKS__</p><p>__COUNTS__</p><table><tr><th>分区数</th><th>禁选层数</th><th>台地占整个域</th><th>台地占可选区域</th></tr>__TABLE__</table><p><a href="samples.csv">逐样本统计</a> · <a href="summary.json">配对核查与来源</a></p>__FIGURES__</main></html>'''
    (target/'report.html').write_text(page.replace('__LINKS__',links).replace('__COUNTS__',count_links).replace('__TABLE__',table).replace('__FIGURES__',figures),encoding='utf-8')
    md=['# 外围禁4层与5层批次对照','',f'[查看全部36份结果]({(target/"report.html").as_posix()})','',
        '| 分区数 | 禁选层数 | 台地占整个域 | 台地占可选区域 |','| --- | --- | --- | --- |']
    for g in groups:
        md.append(f'| {g["partition_count"]} | {g["layer"]} | {g["actual_fraction_range"][0]:.2%} 至 {g["actual_fraction_range"][1]:.2%} | {g["occupied_available_range"][0]:.1%} 至 {g["occupied_available_range"][1]:.1%} |')
    md+=['']+[f'[种子{seed}配对图]({(target/name).as_posix()})' for seed,name in seed_images.items()]
    (target/'comparison.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    return target,groups


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--layers',nargs='+',type=int,default=[4,5]);args=parser.parse_args()
    target,groups=compare(tuple(args.layers))
    print(target);print(groups)
