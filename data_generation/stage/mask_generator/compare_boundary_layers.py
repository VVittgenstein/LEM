"""Compare exact whole-partition reserves using existing, read-only partition maps."""
from pathlib import Path
import argparse,json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--layers',nargs='+',type=int,default=[3,5,10])
    args=parser.parse_args()
    from common.runtime import configure_process_tree
    configure_process_tree(1)
    import numpy as np
    from PIL import Image,ImageDraw
    from common.io import write_json,write_csv,file_sha256,array_sha256,utc_now
    from common.render import font
    from world_orogen.render import boundary_pixels
    from world_orogen_gibbs.config import OUTPUT
    from world_orogen_gibbs.geometry import boundary_reserve
    source=args.source or OUTPUT
    output=args.output or OUTPUT.parent/'world_orogen_boundary_layers'
    output.mkdir(parents=True,exist_ok=True)
    records=[];inputs=[]
    for file in sorted(source.glob('partitions_*/seed*/partitions.npy')):
        count=int(file.parents[1].name.split('_')[1]);seed=int(file.parent.name[4:])
        labels=np.load(file);n=int(labels.max())
        inputs.append(dict(path=str(file),sha256=file_sha256(file)))
        _,distance,depth=boundary_reserve(labels,1)
        base=output/f'partitions_{count}/seed{seed}';base.mkdir(parents=True,exist_ok=True)
        np.save(base/'partition_layers.npy',depth)
        for excluded in args.layers:
            forbidden=depth<=excluded;eligible=(~forbidden)[labels-1]
            target=base/f'layers_{excluded}';target.mkdir(parents=True,exist_ok=True)
            np.save(target/'eligible.npy',eligible)
            # Two exact colors. This array is the eligible domain, not a sampled platform.
            rgb=np.empty((*labels.shape,3),np.uint8);rgb[:]=(65,65,65);rgb[eligible]=(140,204,221)
            Image.fromarray(np.flipud(rgb)).save(target/'eligible.png')
            lines=boundary_pixels(labels);rgb[lines]=(rgb[lines]*.72).astype(np.uint8)
            Image.fromarray(np.flipud(rgb)).save(target/'partitions.png')
            row=dict(seed=seed,partition_count=count,excluded_layers=excluded,
                excluded_regions=int(forbidden.sum()),eligible_regions=int((~forbidden).sum()),
                maximum_layer=int(depth.max()),eligible_cells=int(eligible.sum()),eligible_fraction=float(eligible.mean()),
                minimum_edge_distance_km=float(distance[~forbidden].min()) if eligible.any() else None,
                possible_nonempty_platform=bool(eligible.any()),
                minimum_layer_of_eligible=int(depth[~forbidden].min()) if eligible.any() else None,
                relative_path=target.relative_to(output).as_posix(),
                eligible_array_sha256=array_sha256(eligible))
            if row['possible_nonempty_platform']:
                assert row['minimum_layer_of_eligible']>excluded
            assert not np.r_[eligible[0],eligible[-1],eligible[:,0],eligible[:,-1]].any()
            with Image.open(target/'eligible.png') as image:
                decoded=np.flipud(np.all(np.asarray(image)==(140,204,221),axis=2))
                assert np.array_equal(decoded,eligible)
            write_json(target/'metrics.json',row);records.append(row)
    counts=sorted({r['partition_count'] for r in records});seeds=sorted({r['seed'] for r in records})
    for seed in seeds:
        canvas=Image.new('RGB',(48+524*len(args.layers)-24,100+570*len(counts)),'white');draw=ImageDraw.Draw(canvas)
        draw.text((24,12),f'外围禁选层数对照 · 种子 {seed}',font=font(29),fill='black')
        draw.text((24,53),'灰色为禁选区，浅蓝为剩余可选范围；此图尚未选择台地',font=font(20),fill='black')
        for ri,count in enumerate(counts):
            for ci,excluded in enumerate(args.layers):
                row=next(r for r in records if (r['seed'],r['partition_count'],r['excluded_layers'])==(seed,count,excluded))
                x,y=24+524*ci,100+570*ri
                draw.text((x,y),f'{count} 分区 · 禁选 {excluded} 层',font=font(23),fill='black')
                with Image.open(output/row['relative_path']/'partitions.png') as image:canvas.paste(image,(x,y+35))
                line=f'剩余 {row["eligible_fraction"]:.2%} · {row["eligible_regions"]} 个分区'
                if row['minimum_edge_distance_km'] is not None:line+=f' · 最小距边 {row["minimum_edge_distance_km"]:.0f} km'
                draw.text((x,y+540),line,font=font(17),fill='black')
        canvas.save(output/f'seed{seed}.png')
    groups=[]
    for count in counts:
        for excluded in args.layers:
            group=[r for r in records if r['partition_count']==count and r['excluded_layers']==excluded]
            clearances=[r['minimum_edge_distance_km'] for r in group if r['minimum_edge_distance_km'] is not None]
            groups.append(dict(partition_count=count,excluded_layers=excluded,n=len(group),
                eligible_fraction_range=[min(r['eligible_fraction'] for r in group),max(r['eligible_fraction'] for r in group)],
                median_eligible_fraction=float(np.median([r['eligible_fraction'] for r in group])),
                minimum_clearance_range_km=[min(clearances),max(clearances)] if clearances else None,
                empty_count=sum(not r['possible_nonempty_platform'] for r in group)))
    write_csv(output/'comparisons.csv',records)
    write_json(output/'summary.json',dict(groups=groups,records=records,inputs=inputs,
        definition='outer touching partitions are layer 1; shared pixel-edge adjacency advances one layer',
        scope='eligible domain comparison only; no Gibbs sampling or seabed evolution',
        all_checks_passed=True,case_count=len(records),source_files_unchanged=all(file_sha256(Path(i['path']))==i['sha256'] for i in inputs)))
    def width_text(group):
        value=group['minimum_clearance_range_km']
        return f'{value[0]:g} 至 {value[1]:g}' if value else '无可选区域'
    rows=''.join(f'<tr><td>{g["partition_count"]}</td><td>{g["excluded_layers"]}</td><td>{g["eligible_fraction_range"][0]:.2%} 至 {g["eligible_fraction_range"][1]:.2%}</td><td>{width_text(g)}</td><td>{g["empty_count"]}/{g["n"]}</td></tr>' for g in groups)
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>外围分区层数对照</title><style>body{font:16px/1.7 system-ui,"Microsoft YaHei";margin:24px;color:#1c2b3b;background:#f1f4f7}main{max-width:1620px;margin:auto}img{max-width:100%;image-rendering:pixelated}table{border-collapse:collapse;background:white}td,th{padding:9px 15px;border:1px solid #ccd4dc}a{color:#155d91}summary{cursor:pointer}</style><main><h1>外围禁选 3、5、10 层</h1><p>复用旧批次18张完整分区图。触及域边界算第一层，通过共享边界向内计层。整分区禁选，不裁剪分区。</p><p>灰色为禁选范围，浅蓝为仍可选择台地的范围。这里没有重新抽样台地，也没有计算海底剖面、沉积或抬升。公里数是剩余可选区域到域边缘的最小距离，不能据此保证后续过程始终不出露到边界。</p><table><tr><th>分区数</th><th>禁选层数</th><th>可选面积占整个域</th><th>最小预留距离范围/km</th><th>无可选区</th></tr>__ROWS__</table><p><a href="comparisons.csv">54项逐图统计</a> · <a href="summary.json">定义、来源与核查</a></p>__FIGURES__</main></html>'''
    figures=''.join(f'<h2>种子 {seed}</h2><details'+(' open' if seed==seeds[0] else '')+f'><summary>九组禁选范围</summary><a href="seed{seed}.png"><img src="seed{seed}.png" alt="种子{seed}的九组禁选范围"></a></details>' for seed in seeds)
    (output/'report.html').write_text(page.replace('__ROWS__',rows).replace('__FIGURES__',figures),encoding='utf-8')
    md=['# 外围禁选层数对照','',f'[查看全部对照]({(output/"report.html").as_posix()})','',
        '图中浅蓝为剩余可选区域，尚未抽样台地。灰色分区整块禁选。','',
        '| 分区数 | 禁选层数 | 可选面积范围 | 最小距边界范围/km | 无可选区 |','| --- | --- | --- | --- | --- |']
    for g in groups:
        md.append(f'| {g["partition_count"]} | {g["excluded_layers"]} | {g["eligible_fraction_range"][0]:.2%} 至 {g["eligible_fraction_range"][1]:.2%} | {width_text(g)} | {g["empty_count"]}/{g["n"]} |')
    md+=['',f'[种子1001对照图]({(output/"seed1001.png").as_posix()})']
    (output/'comparison.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    print(json.dumps(groups,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
