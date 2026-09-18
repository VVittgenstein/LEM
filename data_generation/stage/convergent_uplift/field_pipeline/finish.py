import html,zipfile,platform,sys
from context import *

def finish():
    batch=jload(OUT/'batch.json');audit=jload(CHECKS/'audit.json');tests=jload(CHECKS/'tests.json');ds=jload(MODELS/'DS5_model.json');gm=jload(MODELS/'G_geometry_model.json')
    if len(batch['samples'])!=8 or not audit['passed'] or not tests['passed']:raise RuntimeError('Incomplete delivery or failed checks')
    cards=[];summary=[]
    for r in batch['samples']:
        seed=r['seed'];links=[]
        for kind,label in [('A','辅助极值线'),('B','完整二维抬升场')]:
            links.append(f'<a href="seed{seed}/{kind}.png" target="_blank"><img src="seed{seed}/{kind}.png" alt="种子{seed}，{kind}，{label}" loading="lazy"></a>')
        cards.append(f'<section><div class="head"><h2>种子 {seed}</h2><p>辅助线长边 {r["axis_extent_km"]:,.0f} km · 完整场峰值 {r["peak_mm_yr"]:.2f} mm/yr</p></div><div class="pair">'+''.join(links)+f'</div><p class="downloads"><a href="seed{seed}/pair.png">成对原图</a> · <a href="seed{seed}/A.svg">A SVG</a> · <a href="seed{seed}/B.svg">B SVG</a> · <a href="seed{seed}/field.npz">完整数值场</a></p></section>')
        summary.append({'seed':seed,'axis_extent_km':r['axis_extent_km'],'field_peak_mm_yr':r['peak_mm_yr'],
          'target_equivalent_width_km':r['parameters']['width_draw']['value_km'],
          'actual_equivalent_width_km':r['realized_support']['equivalent_width_km'],
          'area_km2':r['realized_support']['area_km2'],'grid_y':r['grid_shape'][0],'grid_x':r['grid_shape'][1]})
    page='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>汇聚抬升场：8组A/B图片</title><style>
    *{box-sizing:border-box}body{margin:0;background:#eef2f5;color:#20303e;font-family:"Microsoft YaHei",sans-serif;line-height:1.65}main{max-width:1680px;margin:auto;padding:32px 24px}h1{font-size:28px;margin:0 0 12px}h2{font-size:19px;margin:0}a{color:#175f93}header{padding:6px 0 22px}header p{margin:8px 0}section{background:white;margin:0 0 24px;border:1px solid #d9e2e8;border-radius:8px;overflow:hidden}.head{display:flex;align-items:center;justify-content:space-between;padding:14px 24px;border-bottom:1px solid #edf0f3;gap:20px}.head p{margin:0;font-size:14px;color:#526374}.pair{display:grid;grid-template-columns:1fr 1fr}.pair a{display:block;min-width:0}.pair img{display:block;width:100%;height:auto}.downloads{padding:0 24px 18px;margin:0;font-size:14px}.evidence{background:white;padding:22px;border-radius:8px}.evidence img{width:100%;height:auto}details{margin-top:18px}summary{cursor:pointer;font-weight:600}.note{color:#526374;font-size:14px}@media(max-width:700px){main{padding:18px 8px}.head{display:block;padding:12px}.pair{grid-template-columns:1fr}.head p{margin-top:4px}h1{font-size:23px}}
    </style></head><body><main><header><h1>汇聚抬升场：8组A/B图片</h1><p>每组A、B使用完全相同的辅助线、坐标范围、绘图区尺寸和比例尺。显示完整活动范围，包含两侧和头尾。</p><p>8组共用查看器FEM色标。图中速率单位为mm/yr；数值文件单位为m/yr。</p><p><a href="eight_pairs_png.zip">下载16张PNG</a> · <a href="eight_pairs_svg.zip">下载16张SVG</a> · <a href="../README.md">方法与统计依据</a> · <a href="../checks/audit.json">数值及图片核查</a></p><p class="note">DS5现代速度统计与G完整造山分区几何用于随机生成。图中虚线为模型作用边界，边界外贡献为0。</p></header>'''+''.join(cards)+'''<div class="evidence"><h2>参考资料与拟合检查</h2><details><summary>DS5剖面及下降曲线拟合</summary><img src="../checks/DS5_fitting.png" alt="DS5来源剖面和拟合曲线"></details><details><summary>G完整区域宽度统计</summary><img src="../checks/G_fitting.png" alt="G宽度统计"></details><details><summary>生成结果与参考统计</summary><img src="../checks/generation_statistics.png" alt="生成结果的统计对照"></details><p class="note">有限边界采用25%参考尾部归零约定，来自63条单侧剖面中的51条可覆盖这一水平。形状迁移、端部几何和空间插值假设详见方法说明。SVG中的场以嵌入栅格保存，辅助线与坐标为矢量。</p></div></main></body></html>'''
    (OUT/'gallery.html').write_text(page,encoding='utf-8');csvsave(OUT/'samples.csv',summary)
    from PIL import Image
    overview=Image.new('RGB',(1600,800*len(batch['samples'])),'white')
    for i,r in enumerate(batch['samples']):
        with Image.open(OUT/f"seed{r['seed']}/pair.png") as im:overview.paste(im.resize((1600,800),Image.Resampling.LANCZOS),(0,800*i))
    overview.save(OUT/'all_eight_pairs.png')
    for ext in ('png','svg'):
        with zipfile.ZipFile(OUT/f'eight_pairs_{ext}.zip','w',zipfile.ZIP_DEFLATED) as z:
            for r in batch['samples']:
                for kind in ('A','B'):
                    p=OUT/f"seed{r['seed']}/{kind}.{ext}";z.write(p,p.relative_to(OUT))
        with zipfile.ZipFile(OUT/f'eight_pairs_{ext}.zip') as z:
            if len(z.namelist())!=16:raise RuntimeError('Incorrect image archive count')
    import numpy,scipy,matplotlib,shapely,pyproj
    jsave(CHECKS/'runtime.json',{'python':sys.version,'executable':sys.executable,'platform':platform.platform(),
         'numpy':numpy.__version__,'scipy':scipy.__version__,'matplotlib':matplotlib.__version__,'shapely':shapely.__version__,'pyproj':pyproj.__version__})
    delivery=['# 8组完整抬升场图片','', '[打开A/B图集](gallery.html) · [16张PNG](eight_pairs_png.zip) · [16张SVG](eight_pairs_svg.zip)', '',
      '种子1001至1008连续生成，未按图形类别或外观筛选。每份B叠加与A相同的辅助线。两图几何由数组与SVG路径回读核查。', '',
      f'DS5：{ds["stations"]}条峰值序列观测、{ds["side_profiles"]}条单侧剖面、{ds["paired_halfwidth_profiles"]}组双侧半高宽；它们来自同一个区域，空间上相关。', '',
      f'下降形态采用{ds["decay_family"]}族，形状参数由拟合概率函数产生。源剖面重建RMSE：'+', '.join(f'{k}={v:.4f}' for k,v in ds['decay_model_comparison_rmse'].items())+'。该值为归一化剖面的重建误差。', '',
      f'原始峰值参考范围{audit["reference_peak_range_mm_yr"][0]:.3f}至{audit["reference_peak_range_mm_yr"][1]:.3f} mm/yr；生成输入范围{audit["generated_input_peak_range_mm_yr"][0]:.3f}至{audit["generated_input_peak_range_mm_yr"][1]:.3f} mm/yr。超出参考范围的尾部为概率模型外推。', '',
      f'{tests["tests"]}项测试通过；8份实际存盘场的种子参数重算和稀疏网格回算通过。数据单位m/yr，显示单位mm/yr。', '',
      '数值检查不等同于地学验收。25%尾部归零、端部几何迁移、空间延伸与重叠规则见[方法说明](../README.md)。']
    (OUT/'delivery.md').write_text('\n'.join(delivery)+'\n',encoding='utf-8')
    inventory=[]
    for p in ROOT.rglob('*'):
        if p.is_file() and not any(q in p.parts for q in ('matplotlib_cache','__pycache__')) and p!=ROOT/'manifest.json' and not any(q.startswith('pilot') for q in p.relative_to(ROOT).parts):
            inventory.append({'path':str(p.relative_to(ROOT)).replace('\\','/'),'bytes':p.stat().st_size,'sha256':sha(p)})
    jsave(ROOT/'manifest.json',{'version':VERSION,'files':inventory,'scope':'field pipeline; earlier axis delivery and retained pilots have separate records'})
    print('Delivery complete:',OUT/'gallery.html',flush=True)

if __name__=='__main__':finish()
