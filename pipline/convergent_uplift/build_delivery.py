"""Create the local gallery and a reproducible delivery manifest."""
import html,json,platform
from pathlib import Path
import numpy,scipy,matplotlib,shapely,pyproj
from common import ROOT,read_json,write_json,sha

def main():
    out=ROOT/'output';run=read_json(out/'run_manifest.json');validation=read_json(ROOT/'checks/validation.json')
    model=read_json(ROOT/'tables/scale_model.json');reference=read_json(ROOT/'tables/geometry_reference.json');samples=run['samples']
    cards=[]
    for r in samples:
        seed=r['seed'];cards.append(f'''<figure><a href="{r['png']}"><img src="{r['png']}" alt="种子{seed}的完整极值线" loading="lazy"></a>
<figcaption><strong>种子 {seed}</strong><span>长边 {r['target_long_km']:,.1f} km · 弧长 {r['total_arc_length_km']:,.1f} km</span>
<span>连通分量 {r['components']} · 三度节点 {r['junctions']} · 回路 {r['cycles']}</span>
<nav><a href="{r['png']}">PNG</a><a href="{r['svg']}">SVG</a><a href="{r['json']}">几何JSON</a><a href="axis_seed{seed}_coordinates_km.csv">坐标CSV</a></nav></figcaption></figure>''')
    gallery='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>完整极值线 · 16种子</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f5f7;color:#193348;font-family:system-ui,"Microsoft YaHei",sans-serif;line-height:1.6}
header,main,footer{max-width:1560px;margin:auto;padding:28px}header h1{margin:0 0 10px;font-size:29px}header p{max-width:1120px;margin:8px 0}
.meta{font-size:14px;color:#496474}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:22px}figure{margin:0;background:white;border:1px solid #dbe2e8;border-radius:9px;overflow:hidden}img{width:100%;height:auto;display:block}figcaption{padding:12px 18px 18px}strong{display:block;font-size:18px}span{display:block;font-size:13px;color:#466174}nav{display:flex;flex-wrap:wrap;gap:16px;margin-top:9px}a{color:#17679d}footer{font-size:13px}code{font-family:monospace}</style></head><body>
<header><h1>完整极值线 · 16个连续种子</h1>
<p>尺度来自G完整造山分区长边的拟合概率模型；主线及局部曲线由有限区域竞争产生。分段、分支和重汇合按固定设计分布抽样，并接受版本化几何检查。</p>
<p class="meta">各图保留实际km刻度，自动显示完整线形。图框不限定为500km。图中线宽为显示样式，尚未生成两侧作用范围或U幅度。</p>
<p class="meta">种子1001至1016依次生成。几何无效的候选保留拒绝记录；没有六类配额、最高分挑选或稀有形态补样。统计代理与设计参数见模块说明。</p>
<nav><a href="delivery.md">交付记录</a><a href="samples.csv">16样本统计</a><a href="../checks/scale_fit.svg">尺度模型</a><a href="../checks/validation.json">核查结果</a><a href="../SOURCE_RULES.md">依据与规则</a></nav>
</header><main class="grid">'''+''.join(cards)+'''</main><footer>本页为本地成果查看页。全部图片、几何数据、来源副本和核查记录位于同一模块目录。</footer></body></html>'''
    (out/'gallery.html').write_text(gallery,encoding='utf-8')
    lines=['# 完整极值线生成交付','',f"正式输出为种子{samples[0]['seed']}至{samples[-1]['seed']}的{len(samples)}组完整极值线，每组附PNG、SVG、JSON和CSV。",'',
      '[打开16图查看页](gallery.html)','',f"保存数据与种子复现检查：{validation['passed']}。尺度样本来自{model['sample_size']}个完整源分区，模型为{model['family']}。几何参照包含{reference['rows']}条筛选后的汇聚相关迹线。",'',
      '尺度指最小旋转外接矩形长边；总弧长另列。每张图自动显示完整坐标范围，保持坐标轴等比例。','',
      '| 种子 | 抽样长边 km | 总弧长 km | 连通分量 | 三度节点 | 回路 | 图 |','|---|---:|---:|---:|---:|---:|---|']
    for r in samples:lines.append(f"| {r['seed']} | {r['target_long_km']:.3f} | {r['total_arc_length_km']:.3f} | {r['components']} | {r['junctions']} | {r['cycles']} | [PNG]({r['png']}) / [SVG]({r['svg']}) |")
    lines += ['', '## 采样与核查','',
      '尺度抽样流与几何随机流独立。一个种子发生几何重试时，其G尺度抽样保持不变。结构计划按固定截断泊松分布生成；各操作位置和几何参数按记录的设计分布生成。拒绝记录保存在各样本JSON中。',
      '',f"本次生成耗时约{run['elapsed_seconds']:.1f}秒。记录的是该环境中本次几何生成与绘图的实际时间。",'',
      '完整性检查包括每个竞争过程都在辅助域内停止、所有自由端点属于生成结构、正式输出无500km裁切。节点、间断、回路、坐标单位、G尺度、SVG点位和全种子重生成分别核对。','',
      '[完整核查JSON](../checks/validation.json) · [运行参数](run_manifest.json) · [规则与来源](../SOURCE_RULES.md)','',
      'G区域尺度到极值线尺度的映射、断层迹线到极值线曲率的借用属于本项目几何近似。分支/分段的频数与多数结构参数保留设计身份；本版规则检查不构成全球地学分布或用户形态验收。','']
    (out/'delivery.md').write_text('\n'.join(lines),encoding='utf-8')
    write_json(ROOT/'checks/runtime.json',{'python':platform.python_version(),'numpy':numpy.__version__,'scipy':scipy.__version__,
      'matplotlib':matplotlib.__version__,'shapely':shapely.__version__,'pyproj':pyproj.__version__})
    files=sorted(p for p in ROOT.rglob('*') if p.is_file() and 'matplotlib_cache' not in p.parts and '__pycache__' not in p.parts and p.name!='module_manifest.json')
    write_json(ROOT/'module_manifest.json',{'files':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]})
    print('Delivery built:',len(samples),'samples;',len(files),'manifest files',flush=True)

if __name__=='__main__':main()
