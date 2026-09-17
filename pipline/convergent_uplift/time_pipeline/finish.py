"""Inspectable local delivery, all trigger records, archives, and manifest."""
import html, zipfile, platform, sys, math
from PIL import Image,ImageDraw,ImageFont
from tcontext import *
from spatial_binding import binding

def traces(directory):
    plt=plotting();event=load(directory/'event.json');p=np.load(directory/'probes.npz');t=p['t_sim_Myr']-event['start_sim_Myr']
    fig,axes=plt.subplots(2,1,figsize=(10,5.4),dpi=160,sharex=True)
    ref=p['reference_u_m_yr'];ids=[int(np.argmin(np.abs(ref-np.quantile(ref,q)))) for q in (.25,.5,.75,.95)]
    for i in ids:axes[0].plot(t,p['u_m_per_yr'][:,i]*1000,lw=1,label=f'定点参考U {ref[i]*1000:.2f} mm/yr')
    axes[0].set_ylabel('抬升速率（mm/yr）');axes[0].legend(ncol=2,fontsize=8)
    axes[1].plot(t,p['u_m_per_yr'].mean(axis=1)*1000,c='#215d7d',label='固定参考范围内探针平均U')
    axes[1].set_ylabel('平均抬升速率（mm/yr）');axes[1].set_xlabel('本次活动已历时间（Myr）')
    right=axes[1].twinx();right.plot(t,(p['u_m_per_yr']>0).mean(axis=1),c='#b98538',ls='--',label='活动探针比例');right.set_ylabel('活动探针比例');right.set_ylim(0,1.05)
    for ax in axes:
        ax.axvline(event['rise_Myr'],c='#888888',ls=':',lw=.8)
        if event['hold_Myr']>0:ax.axvline(event['rise_Myr']+event['hold_Myr'],c='#888888',ls=':',lw=.8)
        ax.set_xlim(0,t[-1]);ax.grid(alpha=.15)
    fig.suptitle(f"样本{event['seed']} · 事件{event['event_index']+1} · 连续时间函数的固定位置检查",fontsize=12)
    fig.text(.09,.015,f"固定{len(ref)}个参考场内探针；参考U分位数决定所画定点。曲线仅覆盖已执行时段。",fontsize=8,color='#566475')
    fig.tight_layout(rect=(0,.04,1,.96));fig.savefig(directory/'traces.png');plt.close(fig)

def main():
    init();batch=load(OUT/'batch.json');audit=load(CHECKS/'audit.json');tests=load(CHECKS/'tests.json')
    assert audit['passed'] and tests['passed'];dur=load(MODELS/'duration.json');rows=[]
    events=[]
    for s in batch['events']:
        p=OUT/f"seed{s['seed']}/event{s['event_index']:02d}";e=load(p/'event.json');events.append((p,e,s));traces(p)
        b=binding(e['seed'],e['event_index'])
        rows.append(dict(seed=e['seed'],event=e['event_index']+1,event_id=e['event_id'],spatial_seed=b['spatial_seed'],axis_extent_km=b['axis_extent_km'],axis_coordinates_sha256=b['axis_coordinates_sha256'],start_age_Ma=e['start_age_Ma'],natural_end_age_Ma=e['natural_end_age_Ma'],
            duration_Myr=e['duration_Myr'],rise_Myr=e['rise_Myr'],hold_Myr=e['hold_Myr'],fall_Myr=e['fall_Myr'],
            ongoing_at_modern=e['ongoing_at_modern'],frames=s['frames'],display_peak_mm_yr=s['frame_peak_mm_yr'],
            actual_multiplier_mean=s['actual_noise_multiplier_mean'],actual_multiplier_cv=s['actual_noise_multiplier_cv'],
            cumulative_P10_m=s['cumulative_executed_P10_P50_P90_m'][0],cumulative_P50_m=s['cumulative_executed_P10_P50_P90_m'][1],
            cumulative_P90_m=s['cumulative_executed_P10_P50_P90_m'][2],cumulative_probe_count=2048,
            crop_first_grid_uplift_sim_Myr=s['crop_first_possible_uplift_sim_Myr']))
    csvsave(OUT/'samples.csv',rows)
    for ext in ('png','svg'):
        with zipfile.ZipFile(OUT/f'all_E_{ext}.zip','w',zipfile.ZIP_DEFLATED) as z:
            for p,e,s in events:z.write(p/f'E.{ext}',f"seed{e['seed']}_event{e['event_index']+1:02d}_E.{ext}")
        with zipfile.ZipFile(OUT/f'all_ABCDE_{ext}.zip','w',zipfile.ZIP_DEFLATED) as z:
            for p,e,s in events:
                for letter in 'ABCDE':
                    src=p/f'E.{ext}' if letter=='E' else p/f'spatial/window/{letter}.{ext}'
                    z.write(src,f"seed{e['seed']}_event{e['event_index']+1:02d}_{letter}.{ext}")
    with zipfile.ZipFile(OUT/'eight_first_E_png.zip','w',zipfile.ZIP_DEFLATED) as z:
        for seed in batch['seeds']:
            p=OUT/f'seed{seed}/E.png'
            if any(e['seed']==seed for _,e,_ in events) and p.exists():z.write(p,f'seed{seed}_E.png')
    cards=[]
    for seed in batch['seeds']:
        group=[x for x in events if x[1]['seed']==seed];parts=[]
        for p,e,s in group:
            path=p.relative_to(OUT).as_posix();end=f"距今{e['natural_end_age_Ma']:.2f} Ma" if e['natural_end_age_Ma']>=0 else f"现代后{-e['natural_end_age_Ma']:.2f} Myr"
            status='现代时仍活动' if e['ongoing_at_modern'] else '在模拟时段内结束'
            parts.append(f'''<article><h3>汇聚抬升事件 {e['event_index']+1} <span>{status}</span></h3>
<p>开始：距今{e['start_age_Ma']:.2f} Ma；自然结束：{end}；总寿命：{e['duration_Myr']:.2f} Myr；实际画面：{s['frames']}。</p>
<nav><a href="{path}/E.png">E图PNG</a><a href="{path}/E.svg">E图SVG</a><a href="{path}/spatial/window/B.png">事件完整场</a><a href="{path}/spatial/window/D.png">事件在数据域中的位置</a><a href="{path}/traces.png">时间曲线</a><a href="{path}/event.json">完整事件记录</a><a href="{path}/summary.json">数值统计</a></nav>
<details><summary>查看本事件的A、B、C、D</summary><a href="{path}/spatial/window/ABCD.png"><img class="figure" src="{path}/spatial/window/preview.png" loading="lazy" alt="本事件独立生成的ABCD图"></a></details>
<a href="{path}/E.png"><img class="figure" src="{path}/preview.png" loading="lazy" alt="种子{seed}活动{e['event_index']+1}的E图"></a></article>''')
        if not group:parts.append('<p>本时段未触发，保留该抽样结果。</p>')
        comparison=f'<p><a href="seed{seed}/belts_in_domain.png">对照同一数据域内的各次事件</a></p>' if len(group)>1 else ''
        cards.append(f'''<section id="seed{seed}"><h2>样本 {seed} · {len(group)} 个独立事件</h2><p>每次触发创建一个完整事件，独立拥有空间形态、作用位置、强度和生命周期。同一事件各帧沿用自己的参数。</p>{comparison}{''.join(parts)}</section>''')
    qs=dur['quantiles_Myr'];future=sum(e['ongoing_at_modern'] for _,e,_ in events);count=sum(s['frames'] for _,_,s in events)
    doc=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>汇聚抬升活动时间管线 · E图</title><style>
:root{{color-scheme:light}}*{{box-sizing:border-box}}body{{margin:0;background:#eef2f5;color:#243447;font:16px/1.7 "Microsoft YaHei",sans-serif}}main{{max-width:1320px;margin:auto;padding:32px 28px}}h1{{font-size:30px;line-height:1.3}}h2{{font-size:23px}}h3{{font-size:19px}}h3 span{{font-size:13px;font-weight:400;background:#edf2f6;padding:4px 9px;border-radius:4px;margin-left:14px}}a{{color:#1d628a;text-decoration:none}}a:hover{{text-decoration:underline}}section,header,.model{{background:white;border-radius:10px;padding:26px 30px;margin-bottom:25px;border:1px solid #dce3e9}}nav{{display:flex;gap:22px;flex-wrap:wrap;margin:14px 0}}article{{border-top:1px solid #dce3e9;padding-top:18px;margin-top:24px}}.figure{{width:100%;height:auto;display:block;margin:16px auto}}.notice{{background:#fff4df;border-left:4px solid #cb9440;padding:15px 18px}}.stats{{color:#526375}}details{{background:#f4f7f9;padding:10px 16px}}summary{{cursor:pointer}}.toplinks{{position:sticky;top:0;background:#eef2f5ed;padding:8px 0;z-index:2}}@media(max-width:700px){{main{{padding:15px}}section,header,.model{{padding:18px}}h1{{font-size:24px}}}}
</style><main><header><h1>汇聚抬升事件的独立生成与连续演化</h1><p class="stats">8个固定数据域 · {len(events)}次触发创建{len(events)}个独立事件 · {count}个场画面 · {future}个事件延续到现代以后</p>
<p>按每阶段完整时长的0%、33%、66%、100%取样，共享时刻合并；现代仍在活动时补现代帧。所有触发均保留，未按结束年代筛选。两条时间轴共用时间比例和现代位置。</p>
<div class="notice">一次触发创建一个新事件，抬升带是该事件的空间作用形态。每个事件拥有自己完整的生成参数并连续演化至自然结束；后续触发创建另一个事件。既有静态示例保留作历史成果，本批事件均独立抽样生成。触发基准、维持及波动参数仍含明确设计取值。</div>
<nav><a href="all_ABCDE_png.zip">全部A至E图PNG</a><a href="all_ABCDE_svg.zip">全部A至E图SVG</a><a href="all_E_png.zip">全部E图PNG</a><a href="all_E_svg.zip">全部E图SVG</a><a href="belts_B_overview.png">13个事件空间场对照</a><a href="event_instances.csv">事件实例表</a><a href="samples.csv">样本统计</a><a href="../models/parameter_provenance.csv">参数依据</a><a href="../README.md">方法说明</a><a href="../checks/audit.json">核查记录</a></nav></header>
<nav class="toplinks">{''.join(f'<a href="#seed{s}">{s}</a>' for s in batch['seeds'])}</nav>
<div class="model"><h2>概率模型与依据</h2><p>自然时长P10 / P50 / P90：{qs['P10']:.1f} / {qs['P50']:.1f} / {qs['P90']:.1f} Myr。该分布描述当前案例约束，全球代表性尚未验证。</p><img class="figure" src="model_overview.png" alt="时长分布与六世触发函数"><nav><a href="../sources/duration_evidence.csv">逐条时长依据</a><a href="../sources/verified_sources.json">原始文献入口</a><a href="../models/duration.json">拟合与敏感性</a><a href="../models/design.json">设计参数</a></nav></div>
{''.join(cards)}<footer>累计量为U的时间积分，原始单位m；终态地表高程需要后续侵蚀、沉积等演化计算。此次未运行完整LEM。源空间输入哈希均已核对。</footer></main></html>'''
    (OUT/'gallery.html').write_text(doc,encoding='utf-8')
    # A compact contact sheet for visual navigation; the scientific E exports remain separate.
    thumbs=[];font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',20)
    for p,e,s in events:
        im=Image.open(p/'preview.png').convert('RGB');im.thumbnail((520,760));tile=Image.new('RGB',(560,815),'white')
        tile.paste(im,((560-im.width)//2,35));ImageDraw.Draw(tile).text((18,7),f"{e['seed']} / 事件{e['event_index']+1}",font=font,fill='#253748');thumbs.append(tile)
    for part in range(math.ceil(len(thumbs)/4)):
        sheet=Image.new('RGB',(1120,1630),'#e8edf1')
        for i,tile in enumerate(thumbs[part*4:(part+1)*4]):sheet.paste(tile,((i%2)*560,(i//2)*815))
        sheet.save(OUT/f'overview_{part+1}.png')
    belt_sheet=Image.new('RGB',(1560,math.ceil(len(events)/3)*550),'#e8edf1')
    for j,(p,e,s) in enumerate(events):
        tile=Image.new('RGB',(520,550),'white');im=Image.open(p/'spatial/window/B.png').convert('RGB');im.thumbnail((520,520))
        tile.paste(im,(0,30));ImageDraw.Draw(tile).text((18,5),f"样本{e['seed']} / 事件{e['event_index']+1}",font=font,fill='#253748')
        belt_sheet.paste(tile,((j%3)*520,(j//3)*550))
    belt_sheet.save(OUT/'belts_B_overview.png')
    for seed in batch['seeds']:
        group=[x for x in events if x[1]['seed']==seed]
        if len(group)<=1:continue
        sheet=Image.new('RGB',(800*len(group),850),'white');draw=ImageDraw.Draw(sheet)
        for j,(p,e,s) in enumerate(group):
            im=Image.open(p/'spatial/window/D.png').convert('RGB');im=im.resize((800,800),Image.Resampling.LANCZOS);sheet.paste(im,(800*j,50))
            draw.text((800*j+24,12),f"样本{seed} · 事件{e['event_index']+1} · 同一500 km数据域",font=font,fill='#253748')
        sheet.save(OUT/f'seed{seed}/belts_in_domain.png')
    delivery=f'''# 时间管线交付记录

8个固定数据域，共{len(events)}次实际触发创建{len(events)}个完整独立事件，{count}个场画面，{future}个事件在现代仍未结束。每个事件独立抽样自己的空间形态、完整U场与窗口，各自提供A至E图。静态示例没有分配给事件。原触发时刻和生命周期保持不变。

时长P10/P50/P90为{qs['P10']:.3f}/{qs['P50']:.3f}/{qs['P90']:.3f} Myr。该结果来自6条约束、4个案例组，包含阶段代理和持续下限。维持及波动参数保持设计身份，未宣称已完成地学总体校准。

{tests['tests']}项行为检查及{len(events)}份逐活动数组、时间、图幅、来源哈希检查通过。视觉检查另见checks/visual_review.json。未运行Fastscape或训练，未修改原空间场、窗口或根目录台账。
'''
    (OUT/'delivery.md').write_text(delivery,encoding='utf-8')
    import scipy,matplotlib
    save(CHECKS/'runtime.json',dict(python=sys.version,executable=sys.executable,numpy=np.__version__,scipy=scipy.__version__,matplotlib=matplotlib.__version__,platform=platform.platform()))
    entries=[]
    for p in sorted(ROOT.rglob('*')):
        if p.is_file() and p!=ROOT/'manifest.json' and '__pycache__' not in p.parts and 'matplotlib_cache' not in p.parts:
            entries.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    save(ROOT/'manifest.json',dict(version=VERSION,files=entries,spatial_sources_manifest='sources/manifest.json',entry_point_sha256=sha(PARENT/'run_time.ps1')))
    print('delivered',len(events),'E figures,',count,'frames',flush=True)

if __name__=='__main__':main()
