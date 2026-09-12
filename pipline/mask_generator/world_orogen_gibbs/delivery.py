import base64
import html
import json
from pathlib import Path
import numpy as np
from PIL import Image
from common.io import read_json,write_json,write_csv,file_sha256,array_sha256,utc_now
from common.contours import extract_contours,rasterize_contours
from world_orogen.render import decode_mask
from .config import Settings
from .geometry import geometry
from .model import terms,conditional
from .metrics import measures
from .render import render_sample,comparison,selected_image


def export_sample(directory):
    directory=Path(directory)
    config=read_json(directory/'config.json')
    settings=Settings.from_record(config)
    labels=np.load(directory/'partitions.npy');g=geometry(labels,settings.boundary_layers);xy=np.load(directory/'seeds.npy')
    with np.load(directory/'fields.npz') as data:fields,combined,average=[data[k] for k in ('fields','combined','average')]
    with np.load(directory/'chain_samples.npz') as data:
        states=data['states'];state=states[0,-1];occurrence=states.mean(axis=(0,1));sweeps=data['sweeps'];statistics=data['statistics']
    mask=state[labels-1];metrics=measures(mask,g,state)
    config.update(boundary_layers=settings.boundary_layers,mask_array_sha256=array_sha256(mask),partition_array_sha256=array_sha256(labels),
        base_fields_array_sha256=array_sha256(fields),combined_field_array_sha256=array_sha256(combined),
        coordinates='local km; x right, y up; origin bottom-left; NPY row 0 at bottom; PNG rows reversed',
        selected_region_ids=(np.flatnonzero(state)+1).tolist(),
        upstream_commit='cc2662b4edd52231c4f65d8765f3ef12cd82d9b7',post_selection_pixel_edits=False)
    write_json(directory/'config.json',config)
    contours=extract_contours(mask);write_json(directory/'contours.json',contours)
    write_json(directory/'metrics.json',metrics)
    probabilities=np.array([conditional(state,i,g,average,settings) for i in range(len(state))])
    write_json(directory/'regions.json',dict(ids=list(range(1,len(state)+1)),
        areas_km2=g.areas*labels.size,centers_xy_km=np.column_stack([g.mx/g.areas+.5,g.my/g.areas+.5])*g.size,
        moments_normalized=dict(mx=g.mx,my=g.my,m2=g.m2),
        adjacency_ids=[[j+1 for j,length in ns] for ns in g.neighbors],
        adjacency_lengths_km=[[length*g.size for j,length in ns] for ns in g.neighbors],
        forbidden=g.forbidden,region_layer=g.region_layer,minimum_domain_edge_distance_km=g.region_clearance_km,
        field_average=average,selected=state,
        empirical_selection_frequency=occurrence,conditional_probability_in_representative=probabilities))
    views=render_sample(directory,g,xy,state,metrics,fields,combined,occurrence,contours,config['seed'])
    write_json(directory/'views.json',views)
    with np.load(directory/'history.npz') as data:
        hstates=data['states'];hsweeps=data['sweeps']
    indexes=np.unique(np.linspace(0,len(states[0])-1,17,dtype=int))
    frames=np.concatenate([hstates,states[0,indexes]],axis=0)
    frame_sweeps=np.r_[hsweeps,sweeps[0,indexes]]
    (directory/'steps').mkdir(exist_ok=True)
    for i,z in enumerate(frames):selected_image(labels,z,g.forbidden).save(directory/'steps'/f'{i:03d}.png')
    np.savez_compressed(directory/'display_states.npz',states=frames,sweeps=frame_sweeps)
    write_viewer(directory,labels,config,metrics,frame_sweeps)
    checks=check_sample(directory)
    write_json(directory/'status.json',dict(execution='complete',data_checks=checks,
        sampling_diagnostics=read_json(directory/'diagnostics.json')['all_passed'],
        appearance_acceptance='pending',observations=[]))
    if not all(checks.values()):raise ValueError(f'failed delivery checks: {directory}: {checks}')
    return dict(seed=config['seed'],partition_count=settings.partition_count,
                relative_path=f'partitions_{settings.partition_count}/seed{config["seed"]}',metrics=metrics,
                diagnostics=read_json(directory/'diagnostics.json'))


def check_sample(directory):
    labels=np.load(directory/'partitions.npy');mask=np.load(directory/'mask.npy')
    with np.load(directory/'chain_samples.npz') as data:states=data['states'];stats=data['statistics']
    z=states[0,-1];m=read_json(directory/'metrics.json');contours=read_json(directory/'contours.json')
    config=read_json(directory/'config.json');settings=Settings.from_record(config)
    g=geometry(labels,settings.boundary_layers)
    with np.load(directory/'fields.npz') as data:field=data['average']
    energy=terms(z,g,field,settings)
    trace=read_json(directory/'last_sweep.json');current=np.array(trace['initial_state'],bool);trace_ok=True
    for update in trace['updates']:
        i=update['region_id']-1
        trace_ok &= bool(current[i])==update['old'] and abs(conditional(current,i,g,field,settings)-update['probability'])<1e-8
        trace_ok &= update['new']==(update['uniform']<update['probability'])
        current[i]=update['new']
    trace_ok &= np.array_equal(current,z)
    checks=dict(shape_dtype=mask.shape==(500,500) and mask.dtype==bool,
        full_domain_partitioned=labels.min()==1 and np.unique(labels).size==len(g.areas),
        every_retained_state_nonempty=states.any(axis=2).all(),
        every_retained_state_excludes_boundary_partitions=not states[:,:,g.forbidden].any(),
        every_retained_state_respects_layer_count=not states[:,:,g.region_layer<=settings.boundary_layers].any(),
        outermost_cells_all_ocean=not np.r_[mask[0],mask[-1],mask[:,0],mask[:,-1]].any(),
        representative_state_matches=np.array_equal(mask,z[labels-1]),
        raw_png_matches=np.array_equal(mask,decode_mask(directory/'mask.png')),
        contour_area=contours['area_km2']==int(mask.sum()),
        contour_valid=contours['valid'],contour_roundtrip=np.array_equal(mask,rasterize_contours(contours)),
        graph_component_count_matches=m['components_4']==int(stats[0,-1,7]),
        graph_largest_area_matches=abs(m['largest_component_fraction']-stats[0,-1,8])<1e-10,
        perimeter_matches=abs(m['all_boundary_grid_km']/500-energy['P'])<1e-10,
        full_energy_matches=abs(energy['total']-stats[0,-1,0])<1e-8,
        complete_last_sweep_trace_replays=trace_ok)
    views=read_json(directory/'views.json')
    with Image.open(directory/'four_stages.png') as image:
        for i,name in enumerate(views['stages']):
            row,col=divmod(i,2);x=24+530*col;y=82+608*row+46
            with Image.open(directory/name) as stage:
                checks[f'stage_{i+1}_tile_matches']=np.array_equal(np.asarray(image.crop((x,y,x+500,y+500))),np.asarray(stage))
    return {k:bool(v) for k,v in checks.items()}


def write_viewer(directory,labels,config,metrics,sweeps):
    regions=read_json(directory/'regions.json')
    data=json.dumps(dict(config=config,metrics=metrics,regions=regions,sweeps=sweeps.tolist()),ensure_ascii=False).replace('<','\\u003c')
    encoded=base64.b64encode(labels.astype('<u2').tobytes()).decode('ascii')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>分区与抽样状态</title>
<style>body{font:16px/1.6 system-ui,"Microsoft YaHei";background:#eef1f5;color:#182736;margin:24px}main{max-width:1150px;margin:auto}a{color:#155e92}.row{display:flex;gap:20px;flex-wrap:wrap}canvas{width:min(100%,750px);height:auto;image-rendering:pixelated;background:#1e1e1e}aside{flex:1;min-width:240px}button,select,input{font:inherit;margin:5px}pre{white-space:pre-wrap;font:13px/1.5 monospace}img{max-width:100%}</style>
<main><a href="../../report.html">返回总览</a><h1 id="title"></h1><p id="facts"></p>
<label>图层 <select id="layer"><option value="mask.png">最终掩膜</option><option value="02_partitions.png">分区与禁选区域</option><option value="03_selection.png">最终分区选择</option><option value="contours.png">全部轮廓</option><option value="field_combined.png">组合随机场</option><option value="field_1.png">15 km 随机场</option><option value="field_2.png">45 km 随机场</option><option value="field_3.png">120 km 随机场</option><option value="selection_frequency.png">抽样中的选中频率</option></select></label>
<p><label>已保存的抽样状态 <input id="step" type="range" min="0" value="0"></label><span id="sweep"></span></p>
<div class="row"><canvas id="map" width="500" height="500"></canvas><aside><strong>鼠标所在分区</strong><pre id="region">移动鼠标查看编号、面积与概率。</pre><p>选中频率来自同一固定随机场下的四条链。条件概率对应最终代表状态。</p><a href="partition_ids.png">完整分区编号图</a> · <a href="seed_ids.png">完整种子编号图</a><pre id="settings"></pre></aside></div>
<p>图层和过程图片均来自保存的产物，页面只显示数据。数组第 0 行在域底部。灰色为按配置层数排除的完整分区。</p></main>
<script type="application/json" id="data">__DATA__</script><script>
'use strict';const data=JSON.parse(document.getElementById('data').textContent),raw=atob('__LABELS__'),labels=new Uint16Array(250000);
for(let i=0;i<labels.length;i++)labels[i]=raw.charCodeAt(2*i)+256*raw.charCodeAt(2*i+1);
const canvas=document.getElementById('map'),ctx=canvas.getContext('2d'),layer=document.getElementById('layer'),step=document.getElementById('step');
let imageVersion=0;function show(path){const version=++imageVersion,img=new Image();img.onload=()=>{if(version===imageVersion)ctx.drawImage(img,0,0);};img.src=path;}
document.getElementById('title').textContent=`种子 ${data.config.seed} · ${data.config.partition_count} 个分区`;
document.getElementById('facts').textContent=`外围禁选 ${data.config.boundary_layers??1} 层，面积 ${(data.metrics.fraction*100).toFixed(2)}%，连通部分 ${data.metrics.components_4}，中心分区 ${data.metrics.initial_center_region_id} ${data.metrics.center_region_selected?'选中':'未选中'}`;
document.getElementById('settings').textContent=JSON.stringify({面积偏好:[.5,.6],随机场权重:data.config.field_weights,位置权重:data.config.center_weight,分散权重:data.config.spread_weight,边界权重:data.config.perimeter_weight},null,2);
step.max=data.sweeps.length-1;step.value=step.max;
layer.addEventListener('change',()=>{show(layer.value);document.getElementById('sweep').textContent='';});
step.addEventListener('input',()=>{show('steps/'+String(step.value).padStart(3,'0')+'.png');document.getElementById('sweep').textContent='第 '+data.sweeps[step.value]+' 轮更新';});
canvas.addEventListener('mousemove',event=>{const box=canvas.getBoundingClientRect(),x=Math.floor((event.clientX-box.left)*500/box.width),y=499-Math.floor((event.clientY-box.top)*500/box.height);if(x<0||x>=500||y<0||y>=500)return;const i=labels[y*500+x]-1,r=data.regions;
document.getElementById('region').textContent=JSON.stringify({编号:i+1,面积_km2:r.areas_km2[i],外围层号:r.region_layer?.[i],最小距边界_km:r.minimum_domain_edge_distance_km?.[i],不可选:r.forbidden[i],最终选中:r.selected[i],平均随机场:r.field_average[i],抽样选中频率:r.empirical_selection_frequency[i],最终条件概率:r.conditional_probability_in_representative[i]},null,2);});show('mask.png');
</script></html>'''
    (directory/'viewer.html').write_text(page.replace('__DATA__',data).replace('__LABELS__',encoded),encoding='utf-8')


def build_delivery(output,refresh_only=False):
    output=Path(output)
    samples=read_json(output/'samples.json') if refresh_only else []
    if not refresh_only:
        for path in sorted(output.glob('partitions_*/seed*/config.json')):
            print('export',path.parent,flush=True);samples.append(export_sample(path.parent))
    counts=sorted({s['partition_count'] for s in samples});seeds=sorted({s['seed'] for s in samples})
    layer_values=sorted({s['metrics'].get('excluded_boundary_layers',1) for s in samples})
    layer_text='、'.join(map(str,layer_values))
    comparison(output,samples,counts,seeds)
    rows=[dict(seed=s['seed'],partition_count=s['partition_count'],
          **{k:s['metrics'][k] for k in ('fraction','components_4','largest_component_fraction','second_component_fraction','center_offset_km','spread_rms_km','center_region_selected','nearest_domain_edge_km')},
          sampling_diagnostics_passed=s['diagnostics']['all_passed']) for s in samples]
    write_csv(output/'samples.csv',rows)
    write_json(output/'samples.json',samples)
    cards=[]
    for s in sorted(samples,key=lambda v:(v['seed'],v['partition_count'])):
        p=s['relative_path'];m=s['metrics']
        cards.append(f'<article><h2>种子 {s["seed"]} · {s["partition_count"]} 分区</h2><p>占比 {m["fraction"]:.2%} · 最大块 {m["largest_component_fraction"]:.1%} · 第二大块 {m["second_component_fraction"]:.1%}</p><a href="{p}/viewer.html">查看分区、随机场、轮廓与更新过程</a> · <a href="{p}/mask.png">原尺寸掩膜</a><details><summary>四阶段图</summary><img src="{p}/four_stages.png" loading="lazy" alt="种子{s["seed"]}的四阶段图"></details></article>')
    review=read_json(output/'visual_review.json') if (output/'visual_review.json').exists() else dict(summary='图像检查进行中。')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>水下台地 Gibbs 选区结果</title><style>body{font:16px/1.65 system-ui,"Microsoft YaHei";margin:24px;background:#f1f4f8;color:#172b40}main{max-width:1150px;margin:auto}article{background:white;padding:18px;margin:20px 0;border:1px solid #d6dfe8;border-radius:7px}img{max-width:100%;image-rendering:pixelated}a{color:#155e92}summary{cursor:pointer}h1{font-size:28px}h2{font-size:21px}</style><main><h1>水下台地整组概率选区</h1><p>500×500，1 km 格距。触边分区整体禁选，中心分区可取消；面积在50%至60%区间内评分相同，区间外仍可出现结果。</p><p>__REVIEW__</p><p><a href="comparison.png">18份分区数量对照</a> · <a href="samples.csv">逐样本统计</a> · <a href="selected_settings.json">参数与试验依据</a> · <a href="pilot/comparison.png">试验参数对照</a> · <a href="delivery_checks.json">数据核查</a></p>__EXTRA____CARDS__<p>五种形态用于观察结果。算法没有按形态标签分配样本，没有填洞、补连接、删除分离部分或按面积修补。所有代表结果采用预先确定的记录位置，未按外观选择。</p></main></html>'''
    page=page.replace('触边分区整体禁选','按配置整层禁选外围分区').replace('18份分区数量对照',f'{len(samples)}份分区数量对照')
    page=page.replace('<h1>水下台地整组概率选区</h1>',f'<h1>水下台地整组概率选区 · 外围禁选 {layer_text} 层</h1>')
    if not (output/'pilot/comparison.png').exists():
        page=page.replace(' · <a href="pilot/comparison.png">试验参数对照</a>','')
    extra='<p><a href="distribution.json">额外种子分布诊断</a> · <a href="diagnostic_comparison.png">额外种子原始掩膜总览</a></p>' if (output/'distribution.json').exists() else ''
    (output/'report.html').write_text(page.replace('__CARDS__',''.join(cards)).replace('__REVIEW__',html.escape(review['summary'])).replace('__EXTRA__',extra),encoding='utf-8')
    lines=[f'# 水下台地整组选区交付 · 外围禁选 {layer_text} 层','',f'{len(samples)} 份四阶段样本，分区数为 '+ '、'.join(map(str,counts))+'。','',
        f'[本地查看页]({(output/"report.html").as_posix()}) · [配对总览]({(output/"comparison.png").as_posix()})','',review['summary'],'',
        '| 种子 | '+' | '.join(f'{n} 分区' for n in counts)+' |','| --- | '+' | '.join('---' for _ in counts)+' |']
    for seed in seeds:lines.append('| '+str(seed)+' | '+' | '.join(f'[四阶段图]({(output/f"partitions_{n}/seed{seed}/four_stages.png").as_posix()})' for n in counts)+' |')
    (output/'delivery.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return samples


def audit_delivery(output):
    output=Path(output);results=[];frames=0
    for file in sorted(output.glob('partitions_*/seed*/config.json')):
        d=file.parent;checks=check_sample(d)
        g=geometry(np.load(d/'partitions.npy'),Settings.from_record(read_json(file)).boundary_layers)
        with np.load(d/'display_states.npz') as data:
            for i,z in enumerate(data['states']):
                expected=np.asarray(selected_image(g.labels,z,g.forbidden))
                with Image.open(d/'steps'/f'{i:03d}.png') as img:
                    if not np.array_equal(expected,np.asarray(img)):raise ValueError('frame mismatch')
                frames+=1
        if not all(checks.values()):raise ValueError(f'audit failed: {d}')
        results.append(dict(path=d.relative_to(output).as_posix(),passed=True,checks=checks))
    import re
    for page in output.glob('**/*.html'):
        for link in re.findall(r'(?:href|src)="([^"]+)"',page.read_text(encoding='utf-8')):
            if link.startswith(('http:','https:','#','data:')):continue
            if (page.parent/link).resolve()==(output/'delivery_checks.json').resolve():continue
            if not (page.parent/link).exists():raise ValueError(f'missing page target: {page}: {link}')
    samples=read_json(output/'samples.json')
    counts=sorted({s['partition_count'] for s in samples});seeds=sorted({s['seed'] for s in samples})
    with Image.open(output/'comparison.png') as overview:
        for sample in samples:
            x=24+524*counts.index(sample['partition_count']);y=110+568*seeds.index(sample['seed'])
            with Image.open(output/sample['relative_path']/'mask.png') as primary:
                if not np.array_equal(np.asarray(overview.crop((x,y,x+500,y+500))),np.asarray(primary)):
                    raise ValueError('comparison tile mismatch')
    paired={}
    for file in output.glob('partitions_*/seed*/config.json'):
        c=read_json(file);paired.setdefault(c['seed'],set()).add(c['base_fields_array_sha256'])
    if any(len(v)!=1 for v in paired.values()):raise ValueError('paired random fields differ')
    value=dict(samples=len(results),frames_verified=frames,results=results,all_passed=True,paired_fields_identical=True,comparison_tiles_match=True,
               browser_interaction='not tested; static data, links and JavaScript syntax are checked separately')
    write_json(output/'delivery_checks.json',value)
    return value
