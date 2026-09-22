"""Reproduce the numerical closeout checks, figure and Markdown report."""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

from .common import ROOT, load, save
from .mesh_study import STUDY, INPUT_NAMES, digest
from .numerical_profile import PROFILE_ID, MESH_PARAMETERS


def checks():
    from .elastic import sample_plane
    source = ROOT/'output/generation_v1/seed1001'
    protocol = load(STUDY/'protocol.json')
    results = []
    def check(name, condition, detail=None):
        results.append(dict(name=name, passed=bool(condition), detail=detail))
    for record in protocol['inputs']:
        check('original_'+record['name'], digest(source/record['name']) == record['sha256'])
        check('frozen_'+record['name'], digest(STUDY/'inputs'/record['name']) == record['sha256'])
    old = np.load(source/'stress_basis.npz')['basis_MPa']
    origin = np.array(load(source/'window.json')['origin_km'])
    xx, yy = np.meshgrid(np.arange(2.5, 500, 5), np.arange(2.5, 500, 5))
    expected = np.array([sample_plane(b, xx+origin[0], yy+origin[1], 2000) for b in old])
    actual = np.load(STUDY/'stress_n65_z5/fields.npz')['basis']
    delta = float(np.max(abs(actual-expected)))
    check('baseline_stress_reproduction', np.allclose(actual, expected, rtol=1e-11, atol=1e-10), delta)
    old_response = np.load(source/'response_basis.npy', mmap_mode='r')[:, 2::5, 2::5, 2]
    actual = np.load(STUDY/'response_n41_z9/fields.npz')['basis']
    relative = float(np.linalg.norm(actual-old_response)/np.linalg.norm(actual))
    check('baseline_response_reproduction', relative < 1e-6, relative)
    generation = STUDY/'generation_n97_z5_s1001'
    previous = [load(p) for p in (generation/'previous_runs').glob('*_result.json')]
    current = load(generation/'result.json')
    check('single_and_parallel_reproducibility', any(p['result_hashes'] == current['result_hashes'] for p in previous))
    fitted = load(generation/'generated/models.json')
    baseline = load(STUDY/'inputs/model_run.json')
    differences = []
    for key in baseline:
        if key == 'design_priors':
            for name, value in baseline[key].items():
                if name not in MESH_PARAMETERS and fitted[key][name] != value:
                    differences.append('design_priors.'+name)
        elif fitted[key] != baseline[key]:
            differences.append(key)
    check('statistical_models_and_physical_design_unchanged', not differences, differences)
    check('selected_profile_applied', fitted['numerical_profile']['id'] == PROFILE_ID and
          all(fitted['design_priors'][k] == v for k, v in MESH_PARAMETERS.items()))
    for seed in range(1001, 1009):
        directory = STUDY/f'generation_n97_z5_s{seed}'
        resource, result = load(directory/'resource.json'), load(directory/'result.json')
        check(f'generation_{seed}', resource['status'] == 'ok' and result['profile']['id'] == PROFILE_ID)
    save(STUDY/'closeout_checks.json', dict(checks=results, passed=all(r['passed'] for r in results)))
    if not all(r['passed'] for r in results):
        raise AssertionError([r for r in results if not r['passed']])
    return results, previous[0]


def main():
    validation, serial = checks()
    summary = load(STUDY/'summary.json')
    entries = {e['tag']: e for e in summary['entries']}
    suites = [load(p) for p in STUDY.glob('suite_*.json')]
    batch = next(s for s in reversed(suites) if len(s['jobs']) == 8 and all(j.startswith('generation:') for j in s['jobs']))
    comparisons = {(c['coarser'], c['finer']): c for c in summary['comparisons']}
    def table(kind, nodes, z):
        rows = []
        for i, n in enumerate(nodes):
            tag = f'{kind}_n{n}_z{z}'
            e = entries[tag]
            difference = '参照端点'
            if i+1 < len(nodes):
                c = comparisons[tag, f'{kind}_n{nodes[i+1]}_z{z}']
                difference = f"{c['relative_l2_max']*100:.2f}%"
            chosen = '采用' if (kind, n) in [('stress', 97), ('response', 65)] else '比较'
            rows.append(f"| {e['horizontal_spacing_km']:.3f} | {n}×{n}×{z} | {e['wall_seconds']:.2f} | {e['peak_rss_bytes']/2**30:.2f} | {difference} | {chosen} |")
        return '\n'.join(rows)
    batchrows = []
    for seed in range(1001, 1009):
        e = entries[f'generation_n97_z5_s{seed}']
        batchrows.append(f"| {seed} | {e['actual_domain_km']} | {e['fault_count']} | {e['timeline_frames']} | {e['wall_seconds']:.2f} | {e['peak_rss_bytes']/2**30:.2f} |")
    os.environ.setdefault('MPLCONFIGDIR', str(ROOT/'output/matplotlib-cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
    plt.rcParams['axes.unicode_minus'] = False
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), layout='constrained')
    for ax, kind, nodes, z, title in zip(axes, ['stress', 'response'], [[65,97,129,161], [41,49,65,81,97]], [5,9], ['应力计算', '断层升降计算']):
        ee = [entries[f'{kind}_n{n}_z{z}'] for n in nodes]
        spacing = [e['horizontal_spacing_km'] for e in ee]
        elapsed = [e['wall_seconds'] for e in ee]
        ax.plot(spacing, elapsed, 'o-', color='#416788')
        selected = 97 if kind == 'stress' else 65
        k = nodes.index(selected)
        ax.scatter([spacing[k]], [elapsed[k]], s=115, color='#ca6d31', zorder=4, label='采用的设计值')
        for x, y in zip(spacing, elapsed):
            ax.annotate(f'{y:.1f} s', (x,y), xytext=(4,7), textcoords='offset points', fontsize=9)
        ax.set(title=title, xlabel='水平计算间距 / km', ylabel='单核实测用时 / s')
        ax.invert_xaxis(); ax.grid(alpha=.2); ax.legend()
    fig.savefig(STUDY/'mesh_cost.png', dpi=160)
    plt.close(fig)
    report = f'''# 裂谷数值配置与收口结果

状态：裂谷阶段已收口。采用`{PROFILE_ID}`作为性能与数值结果之间的设计取值。

用户要求优先寻找性能可接受的收敛区间，未找到时允许选择设计值并收口；现有简化计算已按地学合理设计接受。原话与遗漏的早期完成表态见[本轮依据](../../../docs/work/2026-09-21-rifting-numerical-closeout/decisions.md)。完整LEM接入和终态检验仍属于完整管线阶段。

## 采用的计算配置

| 对象 | 当前设置 | 含义 |
|---|---|---|
| 应力计算 | 97×97×5节点 | 水平每边96段，深度4段；2000 km域的水平间距20.833 km，40 km厚度的深度间距10 km |
| 辅助域候选 | 2000、3000、4000 km | 保持97个水平节点的预算，水平间距相应为20.833、31.25、41.667 km |
| 断层升降计算 | 65×65×9节点 | 1000 km响应域的水平间距15.625 km，深度间距5 km |
| 输出查询 | 500×500，格距1 km | 在计算结果上插值查询；计算间距和输出间距分别保存 |
| 配置身份 | 设计取值 | 未宣称已达到完整数值收敛 |

配置位于[固定配置文件](engine/numerical_profile.py)，拟合入口会把配置标识与实际数值写入每批模型。统计模型、物理源分布、材料、断层滑动规则均保持原有方法。

## 比较方法与范围

固定原种子1001的2000 km辅助域、500 km窗口、10个作用、16条断层及243个时刻，保持力值、作用位置与尺度、材料、边界、断层几何、滑动历史和数值源宽度不变。分别改变水平节点数及深度节点数，共11种配置。全部作用和全部断层参与比较。

采用共同的5 km间距查询位置比较场数组。表中差异为两个计算网格的结果之差的L2范数，除以较细网格结果的L2范数，再取有效时刻中的最大值。应力使用六分量数组；升降使用合成U。近零场时刻单独排除。该值表示网格间差异，相对于真实解的误差未知。

本轮以连续两次加密的最大差异均不超过5%，并通过深度分层检查，作为收敛筛查条件。5%是本轮工程筛查值。单个探索进程限240秒、10 GiB工作集。全部时序、逐断层、累计位移和资源记录保存在[原始汇总](output/numerical_closeout_20260921/summary.json)。

## 水平网格结果

下表每行的差异均与下一行比较，最后一行仅作为已测试的最细参照端点。

### 应力

| 水平间距 km | 节点 | 用时 s | 峰值工作集 GiB | 与下一组最大差异 | 用途 |
|---|---|---|---|---|---|
{table('stress', [65,97,129,161], 5)}

### 断层升降

| 水平间距 km | 节点 | 用时 s | 峰值工作集 GiB | 与下一组最大差异 | 用途 |
|---|---|---|---|---|---|
{table('response', [41,49,65,81,97], 9)}

![网格与计算成本](output/numerical_closeout_20260921/mesh_cost.png)

应力97节点增加到129节点后，耗时从约20秒增至55秒，工作集从约2.5 GiB增至5.0 GiB；继续增加到161节点，工作集达到约8.4 GiB。断层升降65节点增加到81、97节点后，耗时约99、147秒，相邻网格仍有约22%、15%的最大场差异。本轮范围内没有找到同时满足筛查条件和批量成本要求的完整收敛区间。

因此采用中等节点预算作为设计取值：应力97节点、断层升降65节点。该选择提高了原首版65/41节点的空间离散程度，同时保留并行生成所需的内存和时间余量。

## 深度分层

应力在水平97节点下由5层增加到9层，最大场差异10.16%，峰值工作集约9.76 GiB，实测用时约131秒。保留5层作为性能取舍。断层升降在水平65节点下由9层增加到13层，最大场差异2.21%，用时约112秒，保留9层。

两个较细断层配置首次计时曾与其他试验共享CPU亲和性，随后在不同CPU上重测；表格采用重测结果，初次计时保存在对应目录的`previous_runs/`。两次使用相同的冻结输入与计算设置。

## 完整构造输入生成与批量性能

使用新配置从统计模型、作用生成、选窗、条件断层到U响应重新执行输入生成。种子1001单独执行约{serial['compute_seconds']:.2f}秒，生成20条断层、267个展示时刻。此后种子1001至1008各占一个CPU核心并行运行，八份均成功，总实际用时{batch['wall_seconds']:.2f}秒。工作集峰值之和为{batch['peak_rss_sum_upper_bound_bytes']/2**30:.2f} GiB，该值是同时峰值的保守上界。

| 种子 | 辅助域 km | 断层数 | 时刻数 | 并行期间单样本用时 s | 峰值工作集 GiB |
|---|---|---|---|---|---|
{chr(10).join(batchrows)}

计时包含拟合、输入生成、核心数组保存及时间查询检查；不包含完整图集绘制、Fastscape演化或其他活动。批量样本均为2000 km辅助域，本轮没有把结果扩大为其他域尺寸、全部随机种子或完整管线的性能结论。

## 复现与检查

本轮{len(validation)}项专用检查通过：[检查记录](output/numerical_closeout_20260921/closeout_checks.json)。包括原输入与冻结副本哈希、原65/41网格结果复现、统计模型与物理设计保持、配置实际应用、八种子成功以及种子1001单独和并行生成的核心文件哈希一致。

旧图集及其原始数组继续保存在`output/generation_v1/seed1001/`，对应原首版计算设置。新配置的八份核心产物分别位于`output/numerical_closeout_20260921/generation_n97_z5_s<种子>/generated/`，两批产物保持独立身份。

```powershell
# 数值比较程序；已有成功配置会复用，可用 --force 重测
F:\\LEM\\lem-env\\python.exe -B -m engine.mesh_study run
# 汇总与报告，需已有本轮数值、深度及批量结果
F:\\LEM\\lem-env\\python.exe -B -m engine.mesh_study summary
F:\\LEM\\lem-env\\python.exe -B -m engine.mesh_study_report
# 在独立输出目录生成新样本，不改写原图集
.\\run_generation.ps1 -Stage generate -Seed 1001 -OutputDirectory output\\new_batch
```

上述命令在本模块目录执行。所有配置的参数、单次日志和资源记录位于数值试验目录。本轮未执行Git提交或推送。
'''
    (ROOT/'NUMERICAL_CLOSEOUT.md').write_text(report, encoding='utf-8')
    print(json.dumps(dict(checks=len(validation), passed=True, batch_seconds=batch['wall_seconds'],
                          batch_peak_upper_GiB=batch['peak_rss_sum_upper_bound_bytes']/2**30), ensure_ascii=False))


if __name__ == '__main__':
    main()
