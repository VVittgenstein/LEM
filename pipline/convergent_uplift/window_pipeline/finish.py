import zipfile,platform,sys
from html.parser import HTMLParser
from PIL import Image
from wcontext import *

def finish():
    batch=load(OUT/'batch.json');audit=load(CHECKS/'audit.json');tests=load(CHECKS/'tests.json');replay=load(CHECKS/'reproducibility.json')
    if len(batch['samples'])!=8 or not all(x['passed'] for x in (audit,tests,replay)):raise RuntimeError('Delivery incomplete or checks failed')
    cards=[];rows=[]
    for r in batch['samples']:
        seed=r['seed'];s=load(OUT/f'seed{seed}/selection.json')
        cards.append(f'<section id="seed{seed}"><div class="heading"><h2>种子 {seed}</h2><p>跨度 X {s["span_x_km"]:.1f} / Y {s["span_y_km"]:.1f} km · 旋转 {s["rotation_deg"]:.1f}° · 选定归零点余量 {s["witness"]["margin_km"]:.1f} km</p></div><div class="grid">'+''.join(f'<a href="seed{seed}/{k}.png" target="_blank"><img loading="lazy" src="seed{seed}/{k}.png" alt="种子{seed}的{k}图"></a>' for k in 'ABCD')+f'</div><p class="links"><a href="seed{seed}/ABCD.png">四图组合原图</a> · <a href="seed{seed}/window.npz">窗口数据</a> · <a href="seed{seed}/selection.json">本组采样及验证</a></p></section>')
        rows.append({'seed':seed,'span_x_km':s['span_x_km'],'span_y_km':s['span_y_km'],'rotation_deg':s['rotation_deg'],
            'axis_inside_fraction':s['axis_inside_fraction'],'zero_point_margin_km':s['witness']['margin_km'],
            'zero_kind':s['witness']['kind'],'U_max_mm_yr':s['actual_peak_mm_yr'],'eligible_candidates':s['eligible_count'],
            'candidate_count':s['candidate_count'],'overlap_area_km2_diagnostic_only':s['overlap_area_km2']})
    page='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>汇聚抬升随机窗口：8组ABCD</title><style>
    *{box-sizing:border-box}body{margin:0;background:#edf1f5;color:#223444;font-family:"Microsoft YaHei",sans-serif;line-height:1.6}main{max-width:1700px;margin:auto;padding:28px 24px}h1{margin:0 0 10px;font-size:28px}h2{margin:0;font-size:19px}a{color:#175f93}header{padding-bottom:22px}header p{margin:8px 0}section{background:white;margin-bottom:26px;border:1px solid #d9e2e8;border-radius:8px;overflow:hidden}.heading{padding:16px 24px;border-bottom:1px solid #e8edf2}.heading p{margin:6px 0 0;font-size:14px;color:#526577}.grid{display:grid;grid-template-columns:1fr 1fr}.grid img{width:100%;height:auto;display:block}.grid a{min-width:0}.links{padding:0 24px 18px;font-size:14px;margin:0}.note{font-size:14px;color:#526577}.pill{display:inline-block;background:#ffbedb;padding:0 6px;border-radius:3px}nav{display:flex;gap:12px;flex-wrap:wrap}@media(max-width:750px){main{padding:16px 6px}.grid{grid-template-columns:1fr}h1{font-size:22px}.heading{padding:12px}}
    </style></head><body><main><header><h1>汇聚抬升随机窗口：8组ABCD</h1><p>A：辅助线；B：完整场；C：500×500 km红框；D：台地、初始海底与截取场。</p><p>A/B/C共用图幅与比例尺，D显示500 km数据域。B/C/D使用相同FEM色标。<span class="pill">粉色半透明</span>表示台地与抬升作用范围的交集。</p><p>准入条件：窗口内轴线X或Y跨度至少150 km；至少一侧在台地内部自然归零。图D标出经过原函数验证的U=0位置，余量对应这个标记点。</p><p><a href="eight_ABCD_png.zip">下载32张PNG</a> · <a href="eight_ABCD_svg.zip">下载32张SVG</a> · <a href="D_overview.png">8张D图对照</a> · <a href="../README.md">方法与复现</a> · <a href="../checks/audit.json">核查结果</a></p><nav>'''+''.join(f'<a href="#seed{r["seed"]}">{r["seed"]}</a>' for r in rows)+'''</nav><p class="note">随机位置、方向、角度及移动距离均有记录；面积只作输出记录。台地和初始海底由复制的既有管线重新生成，U从原完整场函数取值。</p></header>'''+''.join(cards)+'''</main></body></html>'''
    (OUT/'gallery.html').write_text(page,encoding='utf-8');csvsave(OUT/'samples.csv',rows)
    for ext in ('png','svg'):
        with zipfile.ZipFile(OUT/f'eight_ABCD_{ext}.zip','w',zipfile.ZIP_DEFLATED) as z:
            for row in rows:
                for k in 'ABCD':
                    p=OUT/f"seed{row['seed']}/{k}.{ext}";z.write(p,p.relative_to(OUT))
        with zipfile.ZipFile(OUT/f'eight_ABCD_{ext}.zip') as z:
            if len(z.namelist())!=32:raise ValueError('Incorrect archive size')
    overview=Image.new('RGB',(1600,3200),'white')
    for i,row in enumerate(rows):
        with Image.open(OUT/f"seed{row['seed']}/D.png") as im:overview.paste(im.resize((800,800),Image.Resampling.LANCZOS),((i%2)*800,(i//2)*800))
    overview.save(OUT/'D_overview.png')
    class Links(HTMLParser):
        def __init__(self):super().__init__();self.refs=[]
        def handle_starttag(self,tag,attrs):
            self.refs.extend(v for k,v in attrs if k in ('src','href') and not v.startswith('#'))
    parser=Links();parser.feed(page);missing=[r for r in parser.refs if not (OUT/r).exists()]
    save(CHECKS/'links.json',{'passed':not missing,'count':len(parser.refs),'missing':missing})
    if missing:raise ValueError(missing)
    import scipy,shapely,matplotlib
    save(CHECKS/'runtime.json',{'python':sys.version,'executable':sys.executable,'platform':platform.platform(),'numpy':np.__version__,
      'scipy':scipy.__version__,'shapely':shapely.__version__,'matplotlib':matplotlib.__version__})
    text=['# 8组ABCD交付','', '[打开图集](gallery.html) · [32张PNG](eight_ABCD_png.zip) · [32张SVG](eight_ABCD_svg.zip)','',
      '种子1001至1008。每组A/B/C的辅助线、坐标变换与比例尺相同；C红框每边500 km。D使用复制管线生成的台地与海底数据，并以原连续抬升函数计算窗口值。', '',
      '8项测试、8组数值及图幅检查通过；种子1006完整重跑相同。准入使用投影跨度和一侧自然归零，面积不参与筛选。粉色覆盖为台地与非零U作用范围的交集。','',
      '| 种子 | X跨度 km | Y跨度 km | 选定归零点余量 km |','|---|---:|---:|---:|']
    text.extend(f"| {r['seed']} | {r['span_x_km']:.1f} | {r['span_y_km']:.1f} | {r['zero_point_margin_km']:.1f} |" for r in rows)
    text.extend(['','余量对应图D标记点。其余方向允许延伸出台地。方法、实现参数与边界含义见[说明](../README.md)。'])
    (OUT/'delivery.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    files=[]
    for p in ROOT.rglob('*'):
        if p.is_file() and p!=ROOT/'manifest.json' and not any(k in p.parts for k in ('__pycache__','matplotlib_cache')) and not any(k.startswith('pilot') for k in p.relative_to(ROOT).parts):
            files.append({'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':sha(p),'bytes':p.stat().st_size})
    save(ROOT/'manifest.json',{'version':VERSION,'files':files})
    print('Delivered',len(rows),'ABCD groups;',len(files),'manifest files',flush=True)

if __name__=='__main__':finish()
