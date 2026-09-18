"""A self-contained local viewer with relative links to the saved PNG artifacts."""
from pathlib import Path
import html
import json

from .io import _json_default, read_json


def write_report(output: Path, samples: list[dict]):
    calibration = read_json(output / "calibration/calibration.json")
    audit = read_json(output / "audit.json")
    review_path = output / "visual_review.json"
    review = read_json(review_path) if review_path.is_file() else {"state": "图像检查待记录", "user_acceptance": "待用户检查"}
    unit_path = output / "unit_tests.json"
    unit = read_json(unit_path) if unit_path.is_file() else {"state": "本批次未保存代码测试记录"}
    data = {"samples": samples, "calibration": calibration["selected"], "audit": audit,
            "visual_review": review, "unit_tests": unit}
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False, default=_json_default).replace("<", "\\u003c")
    selected = calibration["selected"]
    page = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>水下台地二维区域掩膜</title>
<style>
:root{color-scheme:light;--ink:#182c40;--muted:#516276;--line:#dce3e9;--paper:#f3f5f8;--accent:#135e87}
*{box-sizing:border-box}body{margin:0;font:15px/1.65 system-ui,"Microsoft YaHei",sans-serif;color:var(--ink);background:var(--paper)}
main{max-width:1280px;margin:auto;padding:28px 24px 64px}h1{font-size:30px;margin:0 0 8px}h2{font-size:22px}p{margin:8px 0}a{color:var(--accent)}
nav,.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center}nav a{background:white;padding:6px 12px;border:1px solid var(--line);border-radius:6px;text-decoration:none}
.intro{max-width:1040px;color:var(--muted);margin-bottom:18px}.controls{position:sticky;top:0;z-index:3;background:#f3f5f8f5;padding:12px 0;border-bottom:1px solid var(--line)}
button,select{font:inherit;padding:7px 11px;border:1px solid #8fabbc;border-radius:5px;background:white;color:var(--ink)}button{cursor:pointer}button[aria-pressed=true]{background:var(--accent);color:white}
.pair{margin-top:26px}.pair-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;gap:10px}.pair-title h2{margin:0}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:20px}.card{border:1px solid var(--line);border-radius:9px;background:white;overflow:hidden}.card h3{font-size:18px;margin:13px 17px 8px}
.mapwrap{background:#162940;padding:0;display:flex;justify-content:center}.map{width:100%;max-width:560px;aspect-ratio:1;image-rendering:pixelated;display:block}
.info{padding:12px 17px 18px}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.metric{font-size:13px;color:var(--muted)}.metric b{display:block;font-size:17px;color:var(--ink);font-variant-numeric:tabular-nums}
.notice{background:#fff6df;border:1px solid #ebd49f;padding:8px 11px;margin-top:10px;color:#694817}.facts{background:white;border:1px solid var(--line);padding:16px 20px;margin-top:20px;border-radius:7px}
details{margin-top:12px}summary{cursor:pointer;color:var(--accent)}pre{font:12px/1.5 Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f7f9;padding:12px;max-height:360px;overflow:auto}
.small{font-size:13px;color:var(--muted)}.key{display:inline-block;width:14px;height:14px;vertical-align:middle;margin-right:5px;border:1px solid #839096}.land{background:rgb(220,230,211)}.sea{background:rgb(22,41,64)}
.figure{max-width:100%;height:auto;background:white}footer{margin-top:36px;border-top:1px solid var(--line);padding-top:14px;color:var(--muted)}
@media(max-width:760px){main{padding:18px 12px}.cards{gap:8px}.card h3{font-size:14px;margin:10px 8px}.info{padding:8px}.metrics{grid-template-columns:1fr 1fr}.metric b{font-size:14px}.pair-title{display:block}h1{font-size:24px}.controls{font-size:13px}}
</style></head><body><main>
<h1>水下台地二维区域掩膜</h1>
<p class="intro">6 个相同种子分别运行两种方法，共 12 份掩膜。每组共享目标占比、位置、方向和三个基础随机场。
尺寸 500×500，格距 1 km；外圈 10 格固定为海洋。此页查看已保存的数据和图片。</p>
<nav><a href="comparison.png">6 行×2 列总览原图</a><a href="reference/aligned_shapes.png">34 个对齐形状</a>
<a href="reference/reference_shapes.png">参考外海岸形状</a><a href="reference/coverage.png">等权叠加包络</a>
<a href="calibration/calibration.json">方法 A 校准记录</a><a href="audit.json">交付核查</a><a href="manifest.json">来源与文件清单</a></nav>
<div class="facts"><p><strong>执行条件</strong>：A 的伸长倍率 __STRETCH__，共同强度倍率 __GAIN__；B 的系数固定为 0.005、0.015、0.050，34 个成员等权，不做校准。</p>
<p><strong>检查状态</strong>：<span id="check-state"></span></p><p id="review-text"></p>
<details><summary>分别查看代码测试、几何检查与外观记录</summary><pre id="validation"></pre></details></div>
<div class="controls" aria-label="查看内容"><span>所有配对切换：</span><div id="views"></div>
<label>定位种子 <select id="jump"><option value="">选择</option></select></label></div>
<p id="legend" class="small"></p><div id="pairs"></div>
<div class="facts"><h2>统计对照</h2><p>方法 A 在固定的 20 组候选中用 64 个共同种子搜索。两项指标各占一份权重。
方法 B 的最终 6 份结果在这里仅作诊断，数值和图片均未用于修改方法 B。</p>
<img class="figure" src="calibration/search.png" alt="方法 A 固定候选误差">
<img class="figure" src="calibration/statistical_comparison.png" alt="面积校正后的两项指标分布对照"></div>
<footer><p><span class="key land"></span>预定水下台地　<span class="key sea"></span>其他区域。图中未赋予海底高程。</p>
<p>原始 PNG 每像素对应一个格子，无插值或平滑。页面缩放采用最近邻显示。NPY 第 0 行对应底部；PNG 顶行对应 NPY 最后一行。
连续场预览可能截断超出色标的颜色，完整数值保存在同名 NPY。参数与检查摘要取自本批次 JSON；页面只读取本地图片，不运行生成函数。</p></footer>
</main><script id="data" type="application/json">__DATA__</script><script>
'use strict';
const data=JSON.parse(document.getElementById('data').textContent);
const views=[['mask','最终掩膜'],['envelope','包络'],['noise_1','1 km 随机场'],['noise_5','5 km 随机场'],['noise_25','25 km 随机场'],['combined','组合场'],['contours','轮廓']];
const fmt=(v,n=3)=>Number(v).toFixed(n);
const el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;};
function metric(name,value){const e=el('div','metric',name);e.append(el('b','',value));return e;}
const review=data.visual_review;
document.getElementById('check-state').textContent=`几何与交付核查${data.audit.passed?'通过':'未通过'}；代码测试 ${data.unit_tests.tests_run??'待记录'} 项；用户外观验收待进行。`;
document.getElementById('review-text').textContent=review.summary??review.state;
document.getElementById('validation').textContent=JSON.stringify({code_tests:data.unit_tests,geometry:data.audit.counts,visual_review:review},null,2);
const seeds=[...new Set(data.samples.map(s=>s.seed))];
for(const seed of seeds){
 const section=el('section','pair');section.id='seed'+seed;const title=el('div','pair-title');
 title.append(el('h2','',`种子 ${seed}`));const pair=data.samples.filter(s=>s.seed===seed);const c=pair[0].config;
 title.append(el('span','small',`共同目标 ${fmt(c.target_fraction*100,4)}% · 方向 ${fmt(c.angle_deg,1)}° · 中心 (${fmt(c.center_x_km,1)}, ${fmt(c.center_y_km,1)}) km`));section.append(title);
 const cards=el('div','cards');
 for(const sample of pair){const m=sample.metrics;const card=el('article','card');
  card.append(el('h3','',sample.method==='ellipse'?'A  椭圆包络＋随机场':'B  参考形状叠加＋随机场'));
  const wrap=el('a','mapwrap');wrap.href=sample.relative_path+'/mask.png';wrap.target='_blank';
  const img=el('img','map');img.src=wrap.href;img.dataset.path=sample.relative_path;img.width=500;img.height=500;img.alt=`种子 ${seed} ${sample.method} 最终掩膜`;wrap.append(img);card.append(wrap);
  const info=el('div','info');const metrics=el('div','metrics');
  metrics.append(metric('实际占比',fmt(m.fraction*100,4)+'%'),metric('长宽比',fmt(m.axis_ratio)),metric('Crofton 岸线系数',fmt(m.shoreline_development)),
  metric('四连通块',m.components_4),metric('最大块占台地',fmt(m.largest_component_fraction*100,2)+'%'),metric('内部空缺格数',m.closed_water_cells));info.append(metrics);
  if(sample.status.issues.length)info.append(el('div','notice',sample.status.issues.map(x=>x.observation).join(' ')));
  const links=el('p','small');for(const file of ['mask.npy','mask.png','contours.json','config.json','metrics.json','status.json']){const a=el('a','',file);a.href=sample.relative_path+'/'+file;links.append(a,document.createTextNode('　'));}info.append(links);
  const details=el('details');details.append(el('summary','','参数与数值来源'),el('pre','',JSON.stringify(sample.config,null,2)));info.append(details);card.append(info);cards.append(card);
 }section.append(cards);document.getElementById('pairs').append(section);
 const option=el('option','',seed);option.value='seed'+seed;document.getElementById('jump').append(option);
}
function switchView(name,label){
 for(const img of document.querySelectorAll('.map')){img.src=img.dataset.path+'/'+name+'.png';img.parentNode.href=img.src;img.alt=img.dataset.path+' '+label;}
 for(const b of document.querySelectorAll('#views button'))b.setAttribute('aria-pressed',String(b.dataset.view===name));
 const descriptions={mask:'固定两色：浅色为台地，深色为其他区域。',contours:'橙色为外轮廓，粉色为内部轮廓；绘制位置为格子边缘。',
 envelope:'线性归一化包络，所有图片色标均为 0 至 1。',combined:'组合场，所有图片色标均为 -0.25 至 1.25。'};
 document.getElementById('legend').textContent=descriptions[name]??'标准化随机场，所有图片色标均为 -3 至 3 个标准差；同一组 A、B 的此图完全相同。';
}
for(const [name,label] of views){const button=el('button','',label);button.dataset.view=name;button.addEventListener('click',()=>switchView(name,label));document.getElementById('views').append(button);}
document.getElementById('jump').addEventListener('change',e=>{if(e.target.value)document.getElementById(e.target.value).scrollIntoView({behavior:'smooth',block:'start'});});
switchView('mask','最终掩膜');
</script></body></html>'''
    page = page.replace("__STRETCH__", html.escape(str(selected["stretch"]))).replace("__GAIN__", html.escape(str(selected["gain"]))).replace("__DATA__", payload)
    (output / "report.html").write_text(page, encoding="utf-8")
