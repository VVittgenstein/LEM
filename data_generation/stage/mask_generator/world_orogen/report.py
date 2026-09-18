"""Static local review page with replay of saved selection-step images."""
import html
import json
from pathlib import Path

from common.io import read_json


def write_report(output:Path,samples,counts):
    config=samples[0]['config']
    data={}
    cards=[]
    count_order=sorted(counts,key=lambda n:(n!=28,n))
    for count in count_order:
        cards.append(f'<section id="p{count}"><h2>{count} 个分区</h2>')
        for index,sample in enumerate(s for s in samples if s['partition_count']==count):
            path=sample['relative_path'];seed=sample['seed'];m=sample['metrics']
            key=f"p{count}s{seed}"
            data[key]=read_json(output/path/'selection.json')['steps']
            maximum=len(data[key])-1
            observations=' '.join(sample['status']['observations'])
            review=sample['status'].get('visual_review',{})
            observations+=' '+' '.join(review.get('observations',[]))
            opened=' open' if index==0 else ''
            cards.append(f'''<article class="sample" id="{key}" data-path="{path}" data-key="{key}">
<h3>种子 {seed} <span>目标 {m['target_fraction']:.2%} · 实际 {m['fraction']:.2%} · 连通部分 {m['components_4']}</span></h3>
<details{opened}><summary>四阶段图</summary><a href="{path}/four_stages.png"><img class="board" src="{path}/four_stages.png" loading="lazy" alt="种子{seed}，{count}个分区的四阶段图"></a></details>
<p class="small">最大连通块占台地 {m['largest_component_fraction']:.2%} · 整体面积中心偏移 {m['centroid_offset_km']:.1f} km · 全部台地到偏好中心的均方根距离 {m['rms_distance_to_preferred_center_km']:.1f} km</p>
<p class="observation">{html.escape(observations)}</p>
<details><summary>逐步查看组合过程及候选概率</summary>
<p><label>选择步骤 <input class="step" type="range" min="0" max="{maximum}" value="{maximum}" aria-label="种子{seed}的选择步骤"></label></p>
<div class="replay"><img class="frame" src="{path}/steps/{maximum:03d}.png" width="500" height="500" alt="已保存的选择步骤">
<div><p class="step-summary"></p><div class="scroll"><table><thead><tr><th>候选分区</th><th>概率</th><th>评分</th></tr></thead><tbody class="candidates"></tbody></table></div>
<p class="small">图片和概率均读取本批次已保存的结果。调节步骤不重新运行随机函数。</p></div></div></details>
<p class="links">{''.join(f'<a href="{path}/{name}">{name}</a> ' for name in ('mask.npy','mask.png','partitions.npy','regions.json','selection.json','config.json','metrics.json','status.json'))}</p>
</article>''')
        cards.append('</section>')
    diagnostic_path=output/'distribution.json'
    diagnostic=read_json(diagnostic_path) if diagnostic_path.exists() else {'status':'not_run'}
    rows=''.join(f"<tr><td>{r['partition_count']}</td><td>{r['n']}</td><td>{r['one_component_count']}</td><td>{r['three_or_more_count']}</td><td>{r['area_above_60_count']}</td><td>{r['median_center_offset_km']:.1f}</td></tr>" for r in diagnostic.get('groups',[]))
    quality=read_json(output/'quality.json') if (output/'quality.json').exists() else {}
    review=read_json(output/'visual_review.json') if (output/'visual_review.json').exists() else {'summary':'图像观察待记录，用户外观验收待进行。'}
    payload=json.dumps(data,ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
    page='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>World Orogen 平面分区与台地选择</title><style>
*{box-sizing:border-box}body{margin:0;background:#f2f4f7;color:#16283d;font:15px/1.65 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1180px;margin:auto;padding:24px 20px 70px}
h1{font-size:29px;margin:0 0 10px}h2{margin-top:30px}h3{font-size:21px;margin:0 0 10px}h3 span{font-size:14px;font-weight:400;margin-left:12px}
a{color:#155e92}nav{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}nav a{padding:5px 12px;border:1px solid #ccd5e0;border-radius:5px;background:white;text-decoration:none}
.facts,.sample{border:1px solid #d9e0e8;border-radius:8px;background:white;padding:18px 20px;margin-top:18px}.board{display:block;width:100%;max-width:1078px;height:auto;image-rendering:pixelated;margin-top:10px}
summary{cursor:pointer;color:#155e92;padding:5px 0}.small{font-size:13px;color:#4c5c70}.observation{background:#fff6df;padding:7px 10px;font-size:14px}.observation:empty{display:none}
.links a{display:inline-block;margin-right:12px;font-size:13px}.replay{display:grid;grid-template-columns:minmax(0,500px) minmax(240px,1fr);gap:18px}.frame{max-width:100%;height:auto;image-rendering:pixelated}input[type=range]{width:65%;vertical-align:middle}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{text-align:left;padding:6px 10px;border-bottom:1px solid #dde4eb}th{background:#eef2f7}.scroll{max-height:410px;overflow:auto}.chosen{background:#dcefd9}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;background:#f3f5f7;padding:12px}footer{margin-top:30px;font-size:13px;color:#4c5c70}@media(max-width:760px){main{padding:18px 10px}.sample{padding:12px}.replay{display:block}h3 span{display:block;margin-left:0}.facts{overflow:auto}}
</style></head><body><main><h1>World Orogen 平面分区与台地选择</h1>
<p>所有结果均为 500×500、1 km 格距。外圈 10 格海洋带固定；按完整分区选择，50% 至 60% 为面积软目标。</p>
<p>同一选择公式用于全部未选分区，位置权重 __CENTER_WEIGHT__、成片权重 __CONNECTION_WEIGHT__。偏好中心为 (__CENTER_X__,__CENTER_Y__) km；未设置形态类别配额。这些数值属于本轮工程试验。</p>
<nav>__NAV__<a href="comparison.png">分区数量对照总图</a>__EXPERIMENT_LINKS__<a href="samples.csv">样本统计</a><a href="quality.json">核查记录</a><a href="manifest.json">来源和文件哈希</a></nav>
<div class="facts"><strong>图像观察</strong><p>__REVIEW__</p><details><summary>执行与数据核查</summary><pre>__QUALITY__</pre></details></div>
__CARDS__
<div class="facts"><h2>额外种子的分布诊断</h2><p class="small">这些结果只保存统计，未参与参数拟合。有限样本中的计数不能确定极小事件概率。</p>
<table><thead><tr><th>分区数</th><th>样本数</th><th>单一连通块</th><th>至少三个连通块</th><th>实际占比超过60%</th><th>中心偏移中位数/km</th></tr></thead><tbody>__DIAGNOSTIC__</tbody></table>
<p>__DIAGNOSTIC_LINKS__<a href="reference_comparison.json">34 个参考陆块的原始统计概况</a></p></div>
<footer>原尺寸 mask.png 使用两种固定颜色，与 mask.npy 可逐格对应。NPY 行号随 y 增大，PNG 顶行对应 NPY 最后一行。
分区连通性整理发生在台地选择前；最终掩膜没有填洞、删除小块或按面积裁剪。自然外观由图像检查与后续验收记录。</footer>
</main><script type="application/json" id="trace-data">__PAYLOAD__</script><script>
'use strict';
const traces=JSON.parse(document.getElementById('trace-data').textContent);
function showStep(input){const card=input.closest('.sample'),step=traces[card.dataset.key][Number(input.value)];
card.querySelector('.frame').src=card.dataset.path+'/steps/'+String(step.step).padStart(3,'0')+'.png';
card.querySelector('.step-summary').textContent=`步骤 ${step.step}，加入分区 ${step.chosen_region}，当步概率 ${(step.chosen_probability*100).toFixed(3)}%，占比 ${(step.fraction*100).toFixed(3)}%，R=${step.R.toFixed(5)}，Q=${step.Q.toFixed(5)}`;
const body=card.querySelector('.candidates');body.replaceChildren();
if(!step.candidate_ids){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=3;td.textContent='初始分区由偏好中心位置确定。';tr.append(td);body.append(tr);return;}
const order=step.candidate_ids.map((id,i)=>i).sort((a,b)=>step.probabilities[b]-step.probabilities[a]);
for(const i of order){const tr=document.createElement('tr');if(step.candidate_ids[i]===step.chosen_region)tr.className='chosen';
for(const value of [step.candidate_ids[i],(step.probabilities[i]*100).toFixed(4)+'%',step.scores[i].toFixed(5)]){const td=document.createElement('td');td.textContent=String(value);tr.append(td);}body.append(tr);}}
for(const input of document.querySelectorAll('.step')){input.addEventListener('input',()=>showStep(input));showStep(input);}
</script></body></html>'''
    substitutions={'__NAV__':''.join(f'<a href="#p{n}">{n} 个分区</a>' for n in count_order),
        '__CENTER_WEIGHT__':f"{config['center_weight']:g}",'__CONNECTION_WEIGHT__':f"{config['connection_weight']:g}",
        '__CENTER_X__':f"{config['center_x_km']:g}",'__CENTER_Y__':f"{config['center_y_km']:g}",
        '__EXPERIMENT_LINKS__':('<a href="weight_comparison_96_32/report.html">56分区较强权重对照</a>'
                                '<a href="weight_comparison.png">同图权重对照总图</a>')
                                if (output/'weight_comparison.png').is_file() else '',
        '__CARDS__':''.join(cards),'__REVIEW__':html.escape(review['summary']),
        '__QUALITY__':html.escape(json.dumps(quality,ensure_ascii=False,indent=2)),
        '__DIAGNOSTIC__':rows,'__PAYLOAD__':payload,
        '__DIAGNOSTIC_LINKS__':'<a href="distribution.csv">逐样本统计</a> · <a href="distribution.json">诊断配置与汇总</a> · ' if diagnostic_path.exists() else '本批次未运行额外种子诊断。'}
    for marker,value in substitutions.items():page=page.replace(marker,value)
    (output/'report.html').write_text(page,encoding='utf-8')
