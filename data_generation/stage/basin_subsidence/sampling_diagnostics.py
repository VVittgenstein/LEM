"""Inspect proposal availability, probability allocation and the actual saved draw."""
import csv
import html
from PIL import Image, ImageDraw, ImageFont
from .common import *
from .window import weight_terms, DESIGN
from .sampling_geometry import platform


def read_candidates(directory):
    with (Path(directory)/'window_candidates.csv').open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def candidate_distribution(directory):
    selection = load(Path(directory)/'selection.json')
    rows = [r for r in read_candidates(directory) if r['status'] == 'eligible']
    probabilities = np.array([float(r['selection_probability']) for r in rows])
    depth = np.array([float(r['normalized_depth']) for r in rows])
    coverage = np.array([float(r['coverage']) for r in rows])
    inside = np.array([r['full_inside_platform'] == 'True' for r in rows])
    histogram = {}
    for name, values, edges in [('depth', depth, np.linspace(0, 1, 21)), ('coverage', coverage, np.linspace(0, .7, 15))]:
        histogram[name] = dict(edges=edges.tolist(), candidate_fraction=(np.histogram(values, edges)[0]/len(rows)).tolist(),
                               selection_probability=np.histogram(values, edges, weights=probabilities)[0].tolist())
    result = dict(eligible_count=len(rows), total_probability=float(probabilities.sum()),
        full_inside_candidate_count=int(inside.sum()), full_inside_probability=float(probabilities[inside].sum()),
        depth_min=float(depth.min()), depth_max=float(depth.max()),
        candidate_mean_depth=float(depth.mean()), weighted_mean_depth=float(probabilities@depth),
        deep_candidate_count=int((depth >= .65).sum()), deep_probability=float(probabilities[depth >= .65].sum()),
        effective_candidate_count=float(1/(probabilities@probabilities)),
        selected_candidate_id=selection['candidate_id'], selected_depth=selection['normalized_depth'],
        selected_coverage=selection['coverage'], selected_full_inside=selection['full_inside_platform'],
        selected_probability=selection['selection_probability'], histogram=histogram,
        identity='distributions over retained traversal proposals; diagnostic depth 0.65 does not gate or classify generation')
    return result, rows


def render_event_sampling(directory):
    plt = plotting(); directory = Path(directory)
    selected = load(directory/'selection.json')
    result, rows = candidate_distribution(directory)
    land = platform(selected['seed'])
    fig, axes = plt.subplots(2, 2, figsize=(13, 10), constrained_layout=True)
    x = np.array([float(r['field_centroid_x_km']) for r in rows])
    y = np.array([float(r['field_centroid_y_km']) for r in rows])
    probabilities = np.array([float(r['selection_probability']) for r in rows])
    axes[0, 0].imshow(land.mask, origin='lower', extent=(0, 500, 0, 500), cmap='Greys', vmin=0, vmax=4)
    points = axes[0, 0].scatter(x, y, c=probabilities*1000, s=7, cmap='viridis', alpha=.6, linewidths=0)
    axes[0, 0].scatter([selected['field_centroid_x_km']], [selected['field_centroid_y_km']],
                       marker='*', c='#cc3434', edgecolors='white', linewidths=.7, s=190, zorder=5, label='本次抽取')
    exterior = np.count_nonzero((x < 0) | (x > 500) | (y < 0) | (y > 500))
    axes[0, 0].set(xlim=(0, 500), ylim=(0, 500), aspect='equal', xlabel='数据域 x（km）', ylabel='数据域 y（km）',
        title=f'合格候选的完整场面积中心\n{len(rows):,} 个；图外中心 {exterior} 个')
    axes[0, 0].legend(fontsize=9, loc='upper left')
    fig.colorbar(points, ax=axes[0, 0], label='单候选抽取概率（‰）', shrink=.78)
    for ax, name, label, chosen in [(axes[0, 1], 'depth', '归一化进入程度 d', selected['normalized_depth']),
                                    (axes[1, 0], 'coverage', '完整参考场覆盖台地的面积比例 c', selected['coverage'])]:
        hist = result['histogram'][name]
        ax.stairs(hist['candidate_fraction'], hist['edges'], color='#8c9ca8', fill=True, alpha=.35, label='合格候选的数量比例')
        ax.stairs(hist['selection_probability'], hist['edges'], color='#187c99', linewidth=2, label='加权后的抽取概率')
        ax.axvline(chosen, color='#cc3434', linestyle='--', label='本次抽取')
        ax.set(xlabel=label, ylabel='区间内比例 / 概率', title='候选分布、选择概率与实际抽取')
        ax.legend(fontsize=8.5)
    for boundary in (.1, .5, .7):
        axes[1, 0].axvline(boundary, color='#a6aeb7', linewidth=.8, linestyle=':')
    axes[1, 0].text(.02, .97, '小事件适用10%下限豁免' if selected['small_event_exemption'] else '10%至70%合格；50%起降低覆盖权重',
                    transform=axes[1, 0].transAxes, va='top', fontsize=9)
    depth = np.linspace(0, 1, 201)
    actual_size = selected['relative_size']
    actual = np.array([weight_terms(1., selected['complete_support_area_km2'], land.area, 0., d, selected['design'])['position_factor'] for d in depth])
    baseline = np.exp(-selected['design']['position_baseline']*depth**2)
    axes[1, 1].plot(depth, actual, color='#187c99', label=f'本事件 s={actual_size:.3f}')
    axes[1, 1].plot(depth, baseline, color='#8c9ca8', linestyle=':', label='尺寸趋近零时的基准衰减')
    axes[1, 1].axvline(selected['normalized_depth'], color='#cc3434', linestyle='--')
    axes[1, 1].set(xlabel='归一化进入程度 d', ylabel='位置权重因子', yscale='log', title='固定完整尺寸下的位置权重')
    axes[1, 1].legend(fontsize=9)
    for ax in axes.ravel():
        ax.grid(alpha=.16)
    fig.suptitle(f"窗口采样诊断 · 数据域 {selected['seed']} · {selected['event_id']}\n"
                 f"完整场位于台地内的候选概率 {result['full_inside_probability']:.1%}；实际结果保留一次随机抽取", fontsize=14)
    fig.savefig(directory/'window_diagnostics.png', dpi=150)
    fig.savefig(directory/'window_diagnostics.svg', metadata={'Date': None})
    plt.close(fig)
    save(directory/'window_diagnostics.json', result)
    return result


def render_sampling_review(output):
    output = Path(output); batch = load(output/'batch.json')
    comparison = load(output/'resampling.json')['comparison'] if (output/'resampling.json').exists() else []
    summaries, table, images = [], [], []
    for row in batch['events']:
        relative = f"seed{row['seed']}/event{row['event_index']:02d}"
        selected = row['selection']
        if 'version' not in selected:
            continue
        result = render_event_sampling(output/relative)
        old = next((r['before'] for r in comparison if r['event_id'] == row['event_id']), None)
        ratio = selected['complete_support_area_km2']/selected['platform_area_km2']
        group = '完整面积 < 台地10%' if ratio < .1 else '台地10% ≤ 完整面积 < 台地50%' if ratio < .5 else '完整面积 ≥ 台地50%'
        flat = dict(event_id=row['event_id'], diagnostic_size_group=group, area_ratio=ratio,
            complete_long_km=row['complete_long_km'], before_coverage=old['coverage'] if old else None,
            before_depth=old['normalized_depth'] if old else None,
            before_full_inside=old['full_inside_platform'] if old else None, **{k:v for k,v in result.items() if k != 'histogram'})
        summaries.append(flat)
        old_text = f"{old['coverage']:.1%} / {old['normalized_depth']:.3f}" if old else '无前次记录'
        where = '完整场位于台地内' if selected['full_inside_platform'] else '部分场位于台地外'
        table.append(f'<tr><td><a href="gallery.html#{row["event_id"]}">{row["event_id"]}</a></td>'
            f'<td>{row["complete_long_km"]:.1f}</td><td>{ratio:.1%}</td><td>{old_text}</td>'
            f'<td>{selected["coverage"]:.1%} / {selected["normalized_depth"]:.3f}</td><td>{where}</td>'
            f'<td>{result["full_inside_probability"]:.1%}</td><td>{result["deep_probability"]:.1%}</td>'
            f'<td><a href="{relative}/window_diagnostics.png">诊断</a> · <a href="{relative}/window_candidates.csv">候选</a>'
            f' · <a href="{relative}/entry_paths.json">轨迹</a></td></tr>')
        images.append((output/relative/'D.png', row['event_id']))
    if not summaries:
        return
    groups = []
    for group in dict.fromkeys(row['diagnostic_size_group'] for row in summaries):
        members = [r for r in summaries if r['diagnostic_size_group'] == group]
        groups.append(dict(group=group, event_count=len(members),
            mean_full_inside_probability=float(np.mean([r['full_inside_probability'] for r in members])),
            expected_full_inside_count=float(sum(r['full_inside_probability'] for r in members)),
            actual_full_inside_count=sum(r['selected_full_inside'] for r in members),
            mean_weighted_depth=float(np.mean([r['weighted_mean_depth'] for r in members])),
            mean_selected_depth=float(np.mean([r['selected_depth'] for r in members]))))
    calibration = [dict(size=s, depth=d, position_factor=float(np.exp(-(DESIGN['position_baseline']+DESIGN['position_size_weight']*s)*d*d)))
                   for s in (0., .25, .5, 1., 2.) for d in (0., .25, .5, .75, 1.)]
    csvsave(output/'window_sampling_summary.csv', summaries)
    save(output/'window_sampling_summary.json', dict(events=summaries, size_groups=groups, position_calibration=calibration,
        identity='size groups are reporting bins; neither generation quotas nor position assignments',
        small_sample_limit='eleven fixed events describe this run and do not estimate a population-level geological frequency'))
    sheet = Image.new('RGB', (2100, 760*int(np.ceil(len(images)/3))), 'white')
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 24)
    for i, (path, label) in enumerate(images):
        x, y = (i % 3)*700, (i//3)*760
        draw.text((x+25, y+12), label, fill='#24394b', font=font)
        with Image.open(path) as source:
            sheet.paste(source.convert('RGB').resize((700, 700), Image.Resampling.LANCZOS), (x, y+45))
    sheet.save(output/'window_sampling_overview.png')
    group_table = ''.join(f'<tr><td>{html.escape(g["group"])}</td><td>{g["event_count"]}</td>'
        f'<td>{g["mean_full_inside_probability"]:.1%}</td><td>{g["expected_full_inside_count"]:.2f}</td>'
        f'<td>{g["actual_full_inside_count"]}</td><td>{g["mean_weighted_depth"]:.3f} / {g["mean_selected_depth"]:.3f}</td></tr>' for g in groups)
    doc = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>沉降窗口采样核对</title><style>body{font:16px/1.7 'Microsoft YaHei',sans-serif;background:#edf2f6;color:#203748;margin:0}main{max-width:1350px;margin:auto;padding:30px}section{background:white;border:1px solid #d6e0e8;border-radius:12px;padding:24px;margin-bottom:20px}img{width:100%;height:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:10px;border-bottom:1px solid #dce4eb;text-align:left}a{color:#176b89}.scroll{overflow-x:auto}code{background:#eef3f7;padding:2px 5px}</style><main><section>
<h1>沉降窗口采样核对</h1><p><a href="gallery.html">返回 A 至 E 图集</a> · <a href="window_sampling_summary.csv">统计表</a> · <a href="window_sampling_summary.json">概率与尺寸分组</a> · <a href="resampling_preservation.json">完整场与时间历史保留核对</a></p>
<p>每个现有事件使用160条穿越轨迹，每条24个分层随机位置。面积筛选以完整成熟期参考场和原始台地为依据。覆盖下限10%，完整场面积不足台地10%的事件豁免下限；覆盖上限70%，从50%起降低覆盖权重。</p>
<p>c 为台地覆盖比例，f 为交集面积除以完整场面积与台地面积中的较小值，b 为窗口内自然归零边界落在台地内的长度比例，s 为完整场面积与台地面积之比的平方根。d 为交集处距台地边界的平均水平距离除以台地最大内部距离，按原1 km像元中心量取，内部水域边界也参与距离计算。</p>
<p><code>log w = 4f + 1.5b − (6 + 6s)d² − 1.5[max(0, (c−0.5)/0.2)]²</code>。四项系数为本轮实现设计值。合格候选的权重归一后抽取一次。尺寸趋近零且d=1时，位置因子约0.00248；相同尺寸仍可抽到不同位置。</p>
<p>候选轨迹的生成分布也参与最终空间分布；权重在这些候选中归一。图集保留全部11次抽取。以下尺寸分组只用于检查，深部诊断阈值d≥0.65只用于统计。该小批次不能证明总体地质频率。</p></section>
<section><h2>逐事件结果</h2><p>覆盖比例与d按“覆盖 / d”排列。“台地内概率”表示完整场全部位于台地内的合格候选总概率。</p><div class="scroll"><table><thead><tr><th>事件</th><th>完整长边 km</th><th>完整面积 / 台地</th><th>修改前覆盖 / d</th><th>本次覆盖 / d</th><th>本次位置</th><th>台地内概率</th><th>深部概率</th><th>记录</th></tr></thead><tbody>'''+''.join(table)+'''</tbody></table></div></section>
<section><h2>按完整尺寸检查</h2><div class="scroll"><table><thead><tr><th>面积分组</th><th>事件数</th><th>平均台地内概率</th><th>期望台地内个数</th><th>本次台地内个数</th><th>加权平均d / 本次平均d</th></tr></thead><tbody>'''+group_table+'''</tbody></table></div></section>
<section><h2>全部500 km数据域</h2><p>每幅D图都使用相同500×500 km数据域；粉色表示场与原始台地的交集。</p><a href="window_sampling_overview.png"><img src="window_sampling_overview.png" alt="全部事件的台地与窗口场"></a></section></main></html>'''
    doc = doc.replace('图集保留全部11次抽取。', f'图集保留全部{len(summaries)}次抽取。')
    if not (output/'resampling_preservation.json').exists():
        doc = doc.replace(' · <a href="resampling_preservation.json">完整场与时间历史保留核对</a>', '')
    (output/'window_sampling_review.html').write_text(doc, encoding='utf-8')
