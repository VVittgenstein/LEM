"""A-E event figures adapted from the accepted convergent display templates."""
import math
import html
import zipfile
import os
import numpy as np
from PIL import Image
from .common import *
from .templates import functions, palette
from .schedule import Event
from .fit import distribution
from .temporal import hazard_increment

def style(edges):
    from matplotlib.colors import ListedColormap, BoundaryNorm
    cmap = ListedColormap(palette())
    cmap.set_bad((0, 0, 0, 0))
    return cmap, BoundaryNorm(edges, 12, clip=True)

def axis_setup(ax, limits):
    from matplotlib.ticker import MaxNLocator
    ax.set_xlim(limits[:2]); ax.set_ylim(limits[2:]); ax.set_aspect('equal', adjustable='box')
    ax.set_xlabel('x（km）'); ax.set_ylabel('y（km）')
    ax.xaxis.set_major_locator(MaxNLocator(5)); ax.yaxis.set_major_locator(MaxNLocator(5))
    ax.grid(alpha=.16, lw=.5)

def scale_bar(fig, span):
    plt = plotting()
    bar = functions()['bar_size'](span)
    width = .72*bar/span; x0 = .11; y0 = .072
    fig.lines.append(plt.Line2D([x0, x0+width], [y0, y0], transform=fig.transFigure, color='#263747', lw=2.3))
    for x in (x0, x0+width):
        fig.lines.append(plt.Line2D([x, x], [y0-.005, y0+.005], transform=fig.transFigure, color='#263747', lw=1.2))
    fig.text(x0+width/2, y0+.011, f'{bar:g} km', ha='center', fontsize=10)
    return bar

def render_reference_detail(directory):
    """Supplementary full-field view for small events inside a 500 km window."""
    plt = plotting(); directory = Path(directory)
    data = np.load(directory/'reference.npz'); mesh = np.load(directory/'mesh.npz')
    field = data['u_m_per_yr']*1000
    bounds = [data['x_km'][0]-.5, data['x_km'][-1]+.5, data['y_km'][0]-.5, data['y_km'][-1]+.5]
    fig, ax = plt.subplots(figsize=(7, 6), constrained_layout=True)
    ax.set_facecolor('#f2f5f8')
    cmap, norm = style(np.linspace(min(-.01, float(field.min())), 0., 13))
    im = ax.imshow(np.ma.masked_where(field == 0, field), origin='lower', extent=bounds, cmap=cmap, norm=norm)
    ax.set(title='完整参考场细节 · 独立诊断色标', xlabel='x（km）', ylabel='y（km）', aspect='equal')
    fig.colorbar(im, ax=ax, label='U（mm/yr）')
    fig.savefig(directory/'reference_detail.png', dpi=150); plt.close(fig)

def render_spatial(directory, color_edges):
    from matplotlib.tri import Triangulation
    from matplotlib.cm import ScalarMappable
    plt = plotting(); directory = Path(directory)
    event, selection, spatial = load(directory/'event.json'), load(directory/'selection.json'), load(directory/'spatial.json')
    mesh = np.load(directory/'mesh.npz'); full = np.load(directory/'reference.npz'); crop = np.load(directory/'window.npz')
    with np.load(BASES/f"seed{event['seed']}/base.npz") as d:
        base = dict(d)
    params = load(SOURCES/'bathymetry_parameters.json')
    cmap, norm = style(color_edges)
    limits = selection['common_extent_km']; native = spatial['field_bounds_km']
    x, y = full['x_km'], full['y_km']; field = full['u_m_per_yr']*1000
    titles = {'A': '生成网格与节点速率', 'B': '完整成熟期参考场', 'C': '500×500 km采样窗口', 'D': '台地、初始海底与截取场'}
    records = []
    for letter in 'ABCD':
        fig = plt.figure(figsize=(8, 8), dpi=180)
        ax = fig.add_axes([.11, .17, .72, .72])
        panel_limits = limits if letter != 'D' else [0, 500, 0, 500]
        axis_setup(ax, panel_limits); ax.set_facecolor('#f4f7fa')
        if letter == 'A':
            points = mesh['points_km']; triangles = mesh['triangles']
            tri = Triangulation(points[:, 0], points[:, 1], triangles)
            ax.triplot(tri, c='#adb8c3', lw=.27, alpha=.60, zorder=1)
            inactive = ~mesh['active']
            ax.scatter(points[inactive, 0], points[inactive, 1], s=2, c='#bdc6ce', linewidths=0, zorder=2)
            ax.scatter(points[~inactive, 0], points[~inactive, 1], s=5, c=mesh['reference_u_m_per_yr'][~inactive]*1000,
                       cmap=cmap, norm=norm, linewidths=0, zorder=2)
            im = ScalarMappable(norm=norm, cmap=cmap)
        elif letter in 'BC':
            im = ax.imshow(np.ma.masked_where(field == 0, field), origin='lower', extent=native,
                           cmap=cmap, norm=norm, interpolation='nearest', zorder=0)
            ax.contour(x, y, full['support'].astype(float), levels=[.5], colors='#344c62', linewidths=.65, linestyles='dashed')
        else:
            functions()['draw_base'](ax, base, params)
            im = ax.imshow(np.ma.masked_where(~crop['support'], crop['u_m_per_yr']*1000), origin='lower', extent=(0, 500, 0, 500),
                           cmap=cmap, norm=norm, interpolation='nearest', zorder=1)
            rgba = np.zeros((500, 500, 4)); rgba[:, :, :3] = [1., .25, .65]; rgba[:, :, 3] = crop['pink_overlap']*.23
            ax.imshow(rgba, origin='lower', extent=(0, 500, 0, 500), interpolation='nearest', zorder=2)
            functions()['base_lines'](ax, base, params)
        if letter == 'C':
            corners = np.array(selection['corners_source_km'])
            ax.plot(corners[:, 0], corners[:, 1], c='#f14343', lw=2.0, zorder=8)
        cax = fig.add_axes([.867, .28, .026, .49])
        cb = fig.colorbar(im, cax=cax, boundaries=color_edges, ticks=color_edges[::2])
        cb.set_label('垂向速率 U（mm/yr）', fontsize=9)
        fig.text(.11, .958, f'{letter}  {titles[letter]}', fontsize=18)
        fig.text(.11, .922, f"数据域 {event['seed']} · 事件 {event['event_index']+1} · 向下为负", fontsize=10, color='#465666')
        bar = scale_bar(fig, panel_limits[1]-panel_limits[0])
        caption = f"完整长边 {spatial['complete_long_km']:.1f} km"
        if letter == 'C':
            caption = f"旋转 {selection['rotation_deg']:.1f}° · 红框每边500 km"
        elif letter == 'D':
            caption = (f"台地覆盖 {selection['coverage']:.1%}" if 'coverage' in selection else
                       f"窗口作用面积 {selection['crop_support_area_km2']:,} km²")
        fig.text(.83, .082, caption, ha='right', fontsize=9, color='#465666')
        note = '外框表示绘图范围；A、B、C共用图幅。C中红框表示500 km数据域。' if letter != 'D' else '粉色：初始台地与事件作用范围的交集；底图高程单位为m。'
        fig.text(.11, .027, note, fontsize=8.8, color='#526373')
        fig.canvas.draw()
        records.append(dict(panel=letter, canvas_px=list(fig.canvas.get_width_height()),
            axes_bbox_px=list(map(float, ax.get_window_extent().bounds)), xlim=list(ax.get_xlim()), ylim=list(ax.get_ylim()),
            scale_bar_km=bar, transform=ax.transData.get_affine().get_matrix().tolist()))
        fig.savefig(directory/f'{letter}.png', dpi=180)
        fig.savefig(directory/f'{letter}.svg', metadata={'Date': None, 'Creator': 'LEM basin subsidence module'})
        plt.close(fig)
    sheet = Image.new('RGB', (2880, 2880), 'white')
    for i, letter in enumerate('ABCD'):
        with Image.open(directory/f'{letter}.png') as image:
            sheet.paste(image.convert('RGB'), ((i % 2)*1440, (i//2)*1440))
    sheet.save(directory/'ABCD.png'); sheet.resize((1800, 1800), Image.Resampling.LANCZOS).save(directory/'ABCD_preview.png')
    save(directory/'display_geometry.json', dict(panels=records, common_extent_km=limits, color_edges_mm_yr=color_edges.tolist(),
        palette='FEM 12', zero_background='zero-valued field cells are transparent over the neutral background',
        color_rgba_uint8=np.round(palette()*255).astype(int).tolist(), window_side_km=500., pink_rgba=[1, .25, .65, .23],
        template_sources=['convergent_render_windows.py: bar_size, draw_base, base_lines'], native_grid_km=1.))

def render_time(directory, color_edges):
    plt = plotting(); directory = Path(directory)
    event, frames = load(directory/'event.json'), load(directory/'frames.json')
    spatial, selection = load(directory/'spatial.json'), load(directory/'selection.json')
    data, full = np.load(directory/'native_frames.npz'), np.load(directory/'reference.npz')
    limits = selection['common_extent_km']; cmap, norm = style(color_edges)
    rows = int(math.ceil(len(frames)/3)); width = 14.; panel = 3.62; left = .88; bottom = 3.95
    gap_x = .66; gap_y = .77; height = bottom+rows*panel+(rows-1)*gap_y+1.55
    fig = plt.figure(figsize=(width, height), dpi=160)
    records = []; numbers = functions()['NUMBERS']
    for i, frame in enumerate(frames):
        row, col = divmod(i, 3); x0 = left+col*(panel+gap_x); y0 = bottom+(rows-1-row)*(panel+gap_y)
        ax = fig.add_axes([x0/width, y0/height, panel/width, panel/height]); axis_setup(ax, limits)
        ax.set_facecolor('#f4f7fa'); U = data['u_m_per_yr'][i]*1000
        im = ax.imshow(np.ma.masked_where(U == 0, U), origin='lower', extent=spatial['field_bounds_km'],
                       cmap=cmap, norm=norm, interpolation='nearest')
        ax.contour(full['x_km'], full['y_km'], full['support'].astype(float), levels=[.5], colors='#9faaba', linewidths=.4, linestyles='dashed')
        corners = np.array(selection['corners_source_km']); ax.plot(corners[:, 0], corners[:, 1], c='#f14343', lw=.8)
        ax.tick_params(labelsize=8); ax.set_xlabel('x（km）', fontsize=8, labelpad=1); ax.set_ylabel('y（km）', fontsize=8, labelpad=1)
        age = '现代 · 0 Ma' if frame['modern'] else f"距今 {frame['age_Ma']:.3f} Ma"
        ax.set_title(f"{numbers[i]} {functions()['stage_label'](frame)}\n{age}", fontsize=10.5, pad=7,
                     color='#a52b3c' if frame['modern'] else '#213344')
        span = limits[1]-limits[0]; bar = functions()['bar_size'](span); bx = limits[0]+.06*span; by = limits[2]+.07*span
        ax.plot([bx, bx+bar], [by, by], c='#253b4e', lw=1.6)
        ax.text(bx+bar/2, by+.025*span, f'{bar:g} km', ha='center', fontsize=8, color='#253b4e')
        ax.text(.98, .015, f"U {U.min():.3f} 至 {U.max():.3f}", transform=ax.transAxes, ha='right', fontsize=7, color='#253b4e')
        records.append((ax, frame, bar))
    cax = fig.add_axes([13.13/width, (bottom+.55)/height, .16/width, max(1.8, rows*panel*.43)/height])
    cb = fig.colorbar(im, cax=cax, boundaries=color_edges, ticks=color_edges[::2]); cb.set_label('U（mm/yr）', fontsize=9); cb.ax.tick_params(labelsize=8)
    fig.text(left/width, 1-.38/height, f"E  沉降事件的时空演化 · 数据域 {event['seed']} · 事件 {event['event_index']+1}", fontsize=17, color='#182d3e')
    fig.text(left/width, 1-.78/height, f"增强 {event['rise_Myr']:.2f} / 维持 {event['hold_Myr']:.2f} / 减弱 {event['fall_Myr']:.2f} Myr"
             f"   |   自然总寿命 {event['duration_Myr']:.2f} Myr", fontsize=10, color='#506273')
    fig.text(left/width, 1-1.10/height, '同一事件的固定历史；外框表示绘图范围，红框表示固定500×500 km数据域。', fontsize=9, color='#506273')
    tax = fig.add_axes([left/width, .73/height, 11.92/width, 2.55/height])
    axis_record = functions()['draw_axes'](tax, event, frames)
    fig.text(left/width, .31/height, '两条时间轴采用相同比例；现代之后保留自然寿命，画面截止现代。灰虚线表示完整参考场范围。', fontsize=9, color='#506273')
    fig.canvas.draw()
    panels = [dict(number=f['number'], sim_Myr=f['sim_Myr'], bbox_px=list(map(float, ax.get_window_extent().bounds)),
                   xlim=list(ax.get_xlim()), ylim=list(ax.get_ylim()), scale_bar_km=bar,
                   transform=ax.transData.get_affine().get_matrix().tolist()) for ax, f, bar in records]
    axis_record['time_to_pixel'] = tax.transData.get_affine().get_matrix().tolist()
    save(directory/'E_geometry.json', dict(panels=panels, timeline=axis_record, color_edges_mm_yr=color_edges.tolist(),
         common_extent_km=limits, template_source='convergent_render_time.py: draw_axes and stage_label; layout adapted'))
    fig.savefig(directory/'E.png', dpi=160); fig.savefig(directory/'E.svg', metadata={'Date': None}); plt.close(fig)
    with Image.open(directory/'E.png') as image:
        image.thumbnail((1200, 2000)); image.save(directory/'E_preview.png')

def render_traces(directory):
    plt = plotting(); directory = Path(directory)
    event = load(directory/'event.json'); evaluator = Event(directory, 'complete')
    ids = np.flatnonzero(evaluator.mesh['active'])
    order = ids[np.argsort(evaluator.mesh['reference_u_m_per_yr'][ids])]
    selected = np.unique(order[np.linspace(0, len(order)-1, 5).astype(int)])
    times = np.linspace(event['start_sim_Myr'], min(48., event['natural_end_sim_Myr']), 193)
    rates = np.array([evaluator.history.rate(t)[selected] for t in times])*1000
    cumulative = np.array([evaluator.history.displacement(event['start_sim_Myr'], t)[selected] for t in times])
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, constrained_layout=True)
    for j, i in enumerate(selected):
        xy = evaluator.mesh['points_km'][i]
        label = f'节点 {i}：({xy[0]:.1f}, {xy[1]:.1f}) km'
        axes[0].plot(times, rates[:, j], label=label); axes[1].plot(times, cumulative[:, j])
    axes[0].set(ylabel='U（mm/yr）', title='固定位置的速率与累计构造位移'); axes[0].legend(fontsize=8)
    axes[1].set(ylabel='累计位移（m）', xlabel='从48 Ma起算的模拟时间（Myr）')
    for ax in axes:
        ax.axhline(0, c='#9ca8b3', lw=.7); ax.grid(alpha=.2)
    fig.savefig(directory/'traces.png', dpi=150); fig.savefig(directory/'traces.svg', metadata={'Date': None}); plt.close(fig)
    trace_data = dict(node_ids=selected, time_Myr=times, U_mm_yr=rates, cumulative_m=cumulative)
    if (directory/'traces.npz').exists():
        with np.load(directory/'traces.npz') as previous:
            unchanged = set(previous.files) == set(trace_data) and all(np.array_equal(previous[k], v) for k, v in trace_data.items())
    else:
        unchanged = False
    if not unchanged:
        np.savez_compressed(directory/'traces.npz', **trace_data)

def render_models(output):
    plt = plotting(); output = Path(output)
    spatial = load(MODELS/'spatial.json'); duration = load(MODELS/'duration.json'); trigger = load(MODELS/'trigger.json')
    data = np.load(MODELS/'reference.npz'); d = distribution(duration['selected']['family'], duration['selected']['parameters'])
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    xx = np.linspace(0, d.ppf(.99), 400); axes[0, 0].plot(xx, d.pdf(xx)); axes[0, 0].set(title='案例约束的自然寿命', xlabel='Myr', ylabel='概率密度（1/Myr）')
    wait = np.linspace(0, 24, 200)
    for i, row in enumerate(trigger['epochs']):
        axes[0, 1].plot(wait, [-np.expm1(-hazard_increment(0, t, i, trigger)) for t in wait], label=row['name'])
    axes[0, 1].set(title='各世允许等待时间与触发概率', xlabel='Myr', ylabel='累计触发概率'); axes[0, 1].legend(fontsize=8)
    axes[1, 0].plot(np.array(spatial['magnitude_quantiles_m_per_Myr'])/1000, spatial['quantile_probabilities'])
    axes[1, 0].set(title='B07平均向下速率的空间分布', xlabel='mm/yr', ylabel='累计概率')
    for j, (a, b) in enumerate(zip(data['old_Ma'], data['young_Ma'])):
        axes[1, 1].plot(data['distance_km'], data['rates_m_per_Myr'][:, j]/1000, lw=.8, label=f'{a:g}至{b:g} Ma')
    axes[1, 1].set(title='原始同位置、分时段剖面', xlabel='沿测线距离（km）', ylabel='向下速率（mm/yr）'); axes[1, 1].legend(fontsize=7, ncol=2)
    for ax in axes.ravel():
        ax.grid(alpha=.2)
    fig.savefig(output/'model_overview.png', dpi=160); fig.savefig(output/'model_overview.svg', metadata={'Date': None}); plt.close(fig)

def render_all(output=OUT):
    output = Path(output); batch = load(output/'batch.json')
    events = batch['events']
    minimum = min([0.]+[min(e['reference_min_mm_yr'], min(f['min_mm_yr'] for f in e['frame_statistics'])) for e in events])
    maximum = max([0.]+[max(e['reference_max_mm_yr'], max(f['max_mm_yr'] for f in e['frame_statistics'])) for e in events])
    # One numeric scale across every event, A-E panel and time frame.
    step = max(.01, np.ceil(max(abs(minimum), maximum)/6/.01)*.01)
    lower = min(-6*step, math.floor(minimum/step)*step)
    upper = max(0., math.ceil(maximum/step)*step)
    edges = np.linspace(lower, upper, 13)
    save(output/'color_scale.json', dict(edges_mm_yr=edges.tolist(), min_displayed_mm_yr=minimum, max_displayed_mm_yr=maximum,
         palette='FEM 12', actual_zero=0., clipping=False))
    for row in events:
        directory = output/f"seed{row['seed']}/event{row['event_index']:02d}"
        render_spatial(directory, edges); render_time(directory, edges); render_traces(directory)
        render_reference_detail(directory)
        print('Rendered A-E:', row['event_id'], flush=True)
    render_models(output)
    from .sampling_diagnostics import render_sampling_review
    render_sampling_review(output)
    finish(output)

def finish(output):
    output = Path(output); batch = load(output/'batch.json'); cards = []
    for row in batch['events']:
        path = f"seed{row['seed']}/event{row['event_index']:02d}"
        event = load(output/path/'event.json')
        selection = row['selection']
        sampling_note, sampling_links = '', ''
        if 'version' in selection:
            sampling_note = (f'<p>台地覆盖 {selection["coverage"]:.1%} · 进入程度 d={selection["normalized_depth"]:.3f} · '
                f'{selection["candidate_count"]:,} 个候选 / {selection["eligible_count"]:,} 个合格 · '
                f'本次候选抽取概率 {selection["selection_probability"]:.3%}</p>')
            sampling_links = (f'<a href="{path}/window_diagnostics.png">窗口采样诊断</a>'
                f'<a href="{path}/window_candidates.csv">全部候选及概率</a><a href="{path}/entry_paths.json">穿越轨迹</a>'
                f'<a href="{path}/selection.json">本次抽取参数</a>')
        modern = '现代仍在活动' if event['ongoing_at_modern'] else '现代之前自然结束'
        cards.append(f'<section id="{row["event_id"]}"><h2>数据域 {row["seed"]} · 事件 {row["event_index"]+1}</h2>'
            f'<p>开始于 {event["start_age_Ma"]:.2f} Ma · 自然寿命 {event["duration_Myr"]:.2f} Myr · {modern} · '
            f'完整长边 {row["complete_long_km"]:.1f} km</p>'+sampling_note+
            f'<a href="{path}/ABCD.png"><img src="{path}/ABCD_preview.png" loading="lazy" alt="A至D完整空间图组"></a>'
            f'<nav>'+''.join(f'<a href="{path}/{letter}.png">{letter} 原图</a>' for letter in 'ABCDE')+
            f'<a href="{path}/traces.png">固定点曲线</a><a href="{path}/reference_detail.png">参考场细节（诊断色标）</a><a href="{path}/summary.json">统计</a><a href="{path}/event.json">事件参数</a>'
            f'<a href="{path}/mesh.npz">网格与节点</a><a href="{path}/native_frames.npz">时间数组</a><a href="{path}/window.npz">窗口数组</a>'+sampling_links+'</nav>'+
            f'<a href="{path}/E.png"><img src="{path}/E_preview.png" loading="lazy" alt="E生命周期与双时间轴"></a></section>')
    doc = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>沉降独立事件图集</title><style>body{margin:0;background:#eef2f5;color:#203748;font:16px/1.65 'Microsoft YaHei',sans-serif}main{max-width:1220px;margin:auto;padding:32px}header,section{background:white;border-radius:12px;padding:24px;margin-bottom:24px;border:1px solid #d6e0e8}h1{margin-top:0}img{display:block;width:100%;height:auto}nav{display:flex;gap:14px;flex-wrap:wrap;margin:15px 0}a{color:#176b89}small{color:#5c6e79}</style><main><header>
<h1>沉降独立事件图集</h1><p>A：生成网格与节点速率；B：完整成熟期参考场；C：实际500×500 km采样窗口；D：台地、初始海底与截取场；E：生命周期与双时间轴。</p>
<p>速率向下为负，单位mm/yr。所有事件和时刻共用FEM色标。各事件固定空间参数与时间历史；每次触发产生独立事件。</p>
<p>A、B、C与E的外框表示自适应绘图范围；C与E的红框表示实际500×500 km数据域。D始终展示该500 km数据域。</p>
<nav><a href="overview.png">全部成熟期场</a><a href="model_overview.png">拟合与原始资料</a><a href="all_ABCDE_png.zip">PNG图组</a><a href="all_ABCDE_svg.zip">SVG图组</a><a href="batch.json">批次记录</a><a href="audit.json">核查记录</a><a href="../README.md">实现说明</a></nav>
<small>当前交付为构造输入生成；完整LEM地形演化属于后续阶段。资料拟合、案例代理和设计参数分别记录。</small></header>'''+''.join(cards)+'</main></html>'
    readme_link = Path(os.path.relpath(ROOT/'README.md', output)).as_posix()
    if (output/'window_sampling_review.html').exists():
        doc = doc.replace('<nav><a href="overview.png">', '<nav><a href="window_sampling_review.html">采样修改前后与概率核对</a><a href="window_sampling_overview.png">全部窗口与台地</a><a href="overview.png">', 1)
    doc = doc.replace('href="../README.md"', f'href="{html.escape(readme_link)}"')
    (output/'gallery.html').write_text(doc, encoding='utf-8')
    n = len(batch['events']); sheet = Image.new('RGB', (1600, max(1, math.ceil(n/4))*420), 'white')
    for i, row in enumerate(batch['events']):
        p = output/f"seed{row['seed']}/event{row['event_index']:02d}/B.png"
        with Image.open(p) as im:
            tile = im.convert('RGB'); tile.thumbnail((400, 400)); sheet.paste(tile, ((i % 4)*400, (i//4)*420))
    sheet.save(output/'overview.png')
    for extension in ('png', 'svg'):
        with zipfile.ZipFile(output/f'all_ABCDE_{extension}.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for row in batch['events']:
                p = output/f"seed{row['seed']}/event{row['event_index']:02d}"
                for letter in 'ABCDE':
                    source = p/f'{letter}.{extension}'
                    archive.write(source, str(source.relative_to(output)))
