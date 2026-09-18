"""Build, export, plot and verify the chronological sea-level master curve."""
import argparse
import copy
import csv
import re
import sys
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from sea_curve import ROOT,CODE,OUTPUT,VERSION,MAX_AGE,KEYS,SeaLevelCurve,write_json,read_json,file_hash


def csv_rows(path,rows):
    rows=list(rows)
    with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def prepare_output(path):
    path=path.resolve();marker=path/'.sea_level.json'
    if CODE not in path.parents:raise ValueError('All results must stay inside the sea_level directory')
    if path.exists() and any(path.iterdir()) and not marker.exists():
        raise ValueError('Existing nonempty output directory has no sea_level identity')
    path.mkdir(parents=True,exist_ok=True)
    if marker.exists() and read_json(marker).get('generator')!='sea_level':raise ValueError('Output identity mismatch')
    if not marker.exists():write_json(marker,dict(generator='sea_level',version=VERSION))
    return path


def join_report(curve):
    joins=[]
    for name,cut,young,old in (('Spratt / Miller未平滑',798000.,KEYS[2],KEYS[1]),
                             ('Miller未平滑 / 平滑',980000.,KEYS[1],KEYS[0])):
        lo,hi=curve.windows['young' if cut==798000 else 'old']
        age=np.linspace(lo,hi,2001);combined=curve.at_age(age);baseline=curve.unblended(age)
        a,b=curve.interpolators[young],curve.interpolators[old]
        input_rate=max(float(np.max(abs(a(age,nu=1)))),float(np.max(abs(b(age,nu=1)))))*1000.
        joins.append(dict(name=name,nominal_join_age_yr_bp=cut,overlap_younger_age_yr_bp=lo,overlap_older_age_yr_bp=hi,
             younger_source=young,older_source=old,younger_source_value_at_join_m=float(a(cut)),
             older_source_value_at_join_m=float(b(cut)),old_minus_young_gap_m=float(b(cut)-a(cut)),
             maximum_abs_adjustment_from_hard_splice_m=float(np.max(abs(combined-baseline))),
             rms_adjustment_from_hard_splice_m=float(np.sqrt(np.mean((combined-baseline)**2))),
             maximum_composite_rate_m_per_kyr=float(np.max(abs(curve.derivative_by_age(age)))*1000),
             maximum_input_rate_m_per_kyr=input_rate))
    boundaries=[]
    for age in sum(curve.windows.values(),[]):
        h=.0001;left_rate=curve.derivative_by_age(age-h);right_rate=curve.derivative_by_age(age+h)
        left_value=curve.at_age(age-h)+h*left_rate;right_value=curve.at_age(age+h)-h*right_rate
        boundaries.append(dict(age_yr_bp=age,sea_level_m=curve.at_age(age),
            value_limit_difference_m=abs(left_value-right_value),rate_difference_m_per_yr=abs(left_rate-right_rate)))
    return dict(interpolation='PCHIP; boundary differences can differ slightly from the preliminary linear interpolation check',
                joins=joins,continuity=boundaries,
                status='local joining choices are engineering processing, not an additional paleoclimate reconstruction')


def window_comparison(curve,out):
    rows=[]
    for width in range(1000,20001,1000):
        bundle=copy.deepcopy(curve.bundle);lo=798000.-width
        bundle['transition_windows_yr_bp']['young']=[lo,798000.]
        trial=SeaLevelCurve(bundle);age=np.linspace(lo,798000.,4001)
        a=trial.interpolators['spratt_2016'];b=trial.interpolators['miller_unsmoothed']
        source_rate=max(float(np.max(abs(a(age,nu=1)))),float(np.max(abs(b(age,nu=1)))))
        joined_rate=float(np.max(abs(trial.derivative_by_age(age))))
        rows.append(dict(window_yr=width,maximum_abs_adjustment_m=float(np.max(abs(trial.at_age(age)-trial.unblended(age)))),
                         maximum_joined_rate_m_per_kyr=joined_rate*1000,maximum_source_rate_m_per_kyr=source_rate*1000,
                         rate_within_source_peak=joined_rate<=source_rate*(1+1e-6)))
    selected=next(v['window_yr'] for v in rows if v['rate_within_source_peak'])
    if selected!=curve.windows['young'][1]-curve.windows['young'][0]:
        raise ValueError('Frozen overlap no longer matches source-based window check')
    write_json(out/'window_comparison.json',dict(candidates=rows,selected_window_yr=selected,
         rule='shortest whole-1-kyr overlap in 1..20 kyr that does not increase the maximum absolute rate above either source in the same interval',
         qualification='engineering choice based on the supplied reconstructions; not a new observation'))
    csv_rows(out/'window_comparison.csv',rows)


def export(curve,out):
    age=np.arange(MAX_AGE,-1.,-1000.);level=curve.at_age(age);weights,_=curve.weights(age)
    baseline=curve.unblended(age);labels=curve.regimes(age)
    elapsed=MAX_AGE-age;rate=-curve.derivative_by_age(age)*1000.
    np.savez_compressed(out/'sea_level_48ma_to_present.npz',age_yr_bp=age,time_from_48ma_yr=elapsed,
         sea_level_m=level,source_weights=weights,unblended_splice_m=baseline,adjustment_m=level-baseline,
         rate_forward_m_per_kyr=rate,source_regime=labels)
    csv_rows(out/'sea_level_48ma_to_present.csv',(dict(age_yr_bp=a,time_from_48ma_yr=t,sea_level_m=z,
         source_regime=label,weight_miller_smoothed=w[0],weight_miller_unsmoothed=w[1],weight_spratt=w[2],
         unblended_splice_m=old,joining_adjustment_m=z-old,rate_forward_m_per_kyr=s)
         for a,t,z,label,w,old,s in zip(age,elapsed,level,labels,weights,baseline,rate)))
    write_json(out/'curve_model.json',curve.bundle)
    native=[]
    for key in KEYS:
        src=curve.bundle['sources'][key]
        for a,z in zip(src['age_yr_bp'],src['sea_level_m']):
            native.append(dict(source=key,age_yr_bp=a,original_sea_level_m=z))
    csv_rows(out/'source_points.csv',native)
    write_json(out/'sources.json',{k:v['metadata'] for k,v in curve.bundle['sources'].items()})
    joins=join_report(curve);write_json(out/'junctions.json',joins);csv_rows(out/'junctions.csv',joins['joins'])
    window_comparison(curve,out)
    # Dense, inspectable adjustments only within the two overlap intervals.
    adjustments=[]
    for name,(lo,hi) in curve.windows.items():
        x=np.arange(lo,hi+1,100.)
        y=curve.at_age(x);b=curve.unblended(x);w,_=curve.weights(x)
        for a,z,old,weight in zip(x,y,b,w):
            adjustments.append(dict(transition=name,age_yr_bp=a,sea_level_m=z,unblended_splice_m=old,
                   adjustment_m=z-old,weight_smoothed=weight[0],weight_unsmoothed=weight[1],weight_spratt=weight[2]))
    csv_rows(out/'joining_adjustments.csv',adjustments)
    return age,level,joins


def figures(curve,out,age,level):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':11,
        'svg.fonttype':'path','svg.hashsalt':'LEM-sea-level-v1','path.simplify':False,
        'axes.spines.top':False,'axes.spines.right':False})
    meta=dict(Date=None,Creator='LEM sea_level',Title='海平面曲线：距今4800万年至现代',
        Description='Chronological composite; ages decrease from 48 Ma BP to present. Miller 2020 PANGAEA.923139 and .923126; Spratt and Lisiecki 2016 NOAA study 19982. Published relative-to-modern datum retained.')
    fig,ax=plt.subplots(figsize=(13.5,5.8),layout='constrained')
    line,=ax.plot(age/1e6,level,color='#163e62',lw=1.25);line.set_gid('master-sea-level-curve')
    ax.axhline(0,color='#8b949b',ls='--',lw=.8)
    ax.scatter([0],[level[-1]],color='#a15b24',s=25,zorder=4)
    ax.set(xlim=(48,0),ylim=(-150,80),xlabel='时间（距今百万年）',ylabel='海平面（m，相对现代海平面）',
           title='海平面曲线：距今4800万年至现代')
    ax.set_xticks([48,45,40,35,30,25,20,15,10,5,0]);ax.set_yticks([-150,-100,-50,0,50])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v,p:'现代' if v==0 else f'{v:g}'))
    ax.grid(alpha=.20)
    ax.text(.015,.96,'Miller平滑版接续未平滑版，再接续Spratt曲线',transform=ax.transAxes,va='top',fontsize=10,color='#53606a')
    fig.savefig(out/'sea_level_48ma_to_present.svg',metadata=meta)
    fig.savefig(out/'sea_level_48ma_to_present.png',dpi=180)
    plt.close(fig)

    fig,axes=plt.subplots(3,1,figsize=(12,10.5),layout='constrained')
    recent=np.linspace(0,1.2e6,6001);axes[0].plot(recent/1e6,curve.at_age(recent),color='#163e62',lw=1.3)
    for lo,hi in curve.windows.values():axes[0].axvspan(lo/1e6,hi/1e6,color='#f3c477',alpha=.32)
    axes[0].set(xlim=(1.2,0),title='最近120万年；浅橙色为局部衔接区',xlabel='时间（距今百万年）',ylabel='海平面（m）')
    for ax,name,cut,young,old,limits in (
        (axes[1],'Spratt与Miller未平滑版',798000.,KEYS[2],KEYS[1],(755000,820000)),
        (axes[2],'Miller未平滑版与平滑版',980000.,KEYS[1],KEYS[0],(955000,1020000))):
        lo,hi=curve.windows['young' if cut==798000 else 'old'];x=np.linspace(*limits,3501)
        for key,label,color in ((young,'较年轻部分的来源','#4f97a0'),(old,'较老部分的来源','#c68d39')):
            src=curve.bundle['sources'][key];mask=(x>=src['age_yr_bp'][0])&(x<=src['age_yr_bp'][-1])
            ax.plot(x[mask]/1000,curve.interpolators[key](x[mask]),color=color,lw=1.,ls='--',label=label)
        ax.plot(x/1000,curve.at_age(x),color='#163e62',lw=1.7,label='接续后的单一曲线')
        ax.axvspan(lo/1000,hi/1000,color='#f3c477',alpha=.25)
        ax.axvline(cut/1000,color='#87939c',lw=.7,ls=':')
        ax.set(xlim=(limits[1]/1000,limits[0]/1000),title=name,xlabel='时间（距今千年）',ylabel='海平面（m）')
        ax.legend(fontsize=9,ncols=3)
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle('海平面曲线衔接检查',fontsize=16)
    fig.savefig(out/'junctions.svg',metadata={**meta,'Title':'海平面曲线衔接检查'})
    fig.savefig(out/'junctions.png',dpi=165);plt.close(fig)


def svg_check(path,age,level):
    root=ET.parse(path).getroot();ns={'s':'http://www.w3.org/2000/svg'}
    group=root.find(".//s:g[@id='master-sea-level-curve']",ns)
    if group is None:raise ValueError('Master data series missing from SVG')
    line=group.find('s:path',ns)
    number=r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?'
    points=np.array([(float(a),float(b)) for a,b in re.findall(r'[ML]\s*('+number+r')\s+('+number+r')',line.attrib['d'])])
    if len(points)!=len(age):raise ValueError(f'SVG preserved {len(points)} of {len(age)} data points')
    x,y=points.T
    expected_x=x[0]+(age-age[0])*(x[-1]-x[0])/(age[-1]-age[0])
    zz=level-level.mean();yy=y-y.mean();slope=float(zz@yy/(zz@zz))
    expected_y=y.mean()+slope*zz
    ex=float(np.max(abs(x-expected_x)));ey=float(np.max(abs(y-expected_y)))
    external=[]
    for el in root.iter():
        for key,value in el.attrib.items():
            if key.endswith('href') and not value.startswith('#'):external.append(value)
    return dict(vertices=len(points),time_axis_forward=bool((np.diff(x)>0).all()),
         height_axis_correct=slope<0,max_time_mapping_error_svg_units=ex,max_height_mapping_error_svg_units=ey,
         external_render_resources=external,
         passed=bool(ex<2e-5 and ey<2e-5 and slope<0 and (np.diff(x)>0).all() and not external))


def verify(curve,out,age,level,tests,joins):
    with np.load(out/'sea_level_48ma_to_present.npz',allow_pickle=False) as data:
        npz_ok=np.array_equal(data['sea_level_m'],level) and np.array_equal(data['age_yr_bp'],age)
    with (out/'sea_level_48ma_to_present.csv').open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    csv_ok=np.array_equal(np.array([float(r['sea_level_m']) for r in rows]),level)
    restored=SeaLevelCurve.from_bundle(out/'curve_model.json')
    repeat=np.array_equal(restored.at_age(age),level)
    source_ok=all(file_hash(v['metadata']['path'])==v['metadata']['sha256'] for v in curve.bundle['sources'].values())
    svg=svg_check(out/'sea_level_48ma_to_present.svg',age,level)
    continuous=all(v['value_limit_difference_m']<1e-8 and v['rate_difference_m_per_yr']<1e-8 for v in joins['continuity'])
    checks=dict(tests=tests['passed'],full_48ma_to_present=age[0]==MAX_AGE and age[-1]==0 and len(age)==48001,
         finite=np.isfinite(level).all(),unique_monotone_ages=(np.diff(age)<0).all(),npz_readback=npz_ok,
         csv_readback=csv_ok,bundle_reproduction=repeat,sources_unchanged=source_ok,
         joins_continuous=continuous,svg_matches_data=svg['passed'])
    result=dict(checks=checks,svg=svg,passed=bool(all(checks.values())),
         min_sea_level_m=float(level.min()),max_sea_level_m=float(level.max()),modern_estimate_m=float(level[-1]),
         original_datum_retained=True,
         output_sampling_note='1 kyr is the uniform export interval; source information resolution remains age dependent')
    write_json(out/'validation.json',result)
    if not result['passed']:raise RuntimeError('Sea-level export validation failed')
    return result


def report(out,curve,validation,joins):
    lines=['# 单一海平面曲线：距今4800万年至现代','',
      '该曲线按年代顺序接续三个资料段。完整主图为 `sea_level_48ma_to_present.svg`，另附PNG预览与两处接点放大图。','',
      '| 年代范围 | 来源或处理 |','|---|---|',
      '| 4800万年至100万年前 | Miller平滑版 |',
      '| 100万年至98万年前 | 平滑版与未平滑版的局部渐变 |',
      '| 98万年至79.8万年前 | Miller未平滑版 |',
      '| 79.8万年至79.4万年前 | 未平滑版与Spratt的局部渐变 |',
      '| 79.4万年前至现代 | Spratt五记录堆叠版 |','',
      '较老过渡为2万年，对应Miller平滑资料一个采样间隔。较新过渡为4千年：比较1千至2万年的窗口，选取未增加同区间原资料峰值升降速率的最短窗口。比较见window_comparison.json。这些窗口属于工程衔接规则。采用保持数据形状的PCHIP插值及五次平滑权重，交接处高程和一阶变化率连续。',
      '', '| 接点 | 较年轻来源 m | 较老来源 m | 较老减较年轻 m | 过渡区最大改动 m |','|---|---:|---:|---:|---:|']
    for j in joins['joins']:
        lines.append(f'| {j["nominal_join_age_yr_bp"]/10000:g}万年前 | {j["younger_source_value_at_join_m"]:.4f} | {j["older_source_value_at_join_m"]:.4f} | {j["old_minus_young_gap_m"]:.4f} | {j["maximum_abs_adjustment_from_hard_splice_m"]:.4f} |')
    lines+=['','改动量相对于在98万年、79.8万年直接切换资料的未融合序列计算；与初步线性插值核查的数值存在小差别。区外保留所选原资料的插值曲线及原始节点值，区内改动逐点保存于 `joining_adjustments.csv`。',
      '',f'统一输出步距1000年，共48001点；高程范围 {validation["min_sea_level_m"]:.2f} 至 {validation["max_sea_level_m"]:.2f} m。现代端点保留Spratt原始重建值 {validation["modern_estimate_m"]:.2f} m。',
      '较老段仍具有Miller平滑数据的2万年间距及已平滑信息尺度；插值为1000年步距没有增加该时期的原始信息。Miller未平滑桥接段沿用不等间隔原数据。',
      '源资料采用发布的相对现代高程基准和年代模型。重建差异保留在来源和接点记录中，本轮未增加年龄校正或对整段资料施加额外垂直偏移。Spratt的不确定度保存在模型包中，未为整个拼接曲线推算新的置信区间。',
      '', '模拟时通过 `SeaLevelCurve.window(start_age_yr_bp, duration_yr)` 截取同一曲线，年代随模拟时间递减；默认减去所选区间起点值，使初始海平面为0 m。超出0至4800万年范围的请求会报错。',
      '',f'核查结果：{validation["passed"]}。覆盖、接点连续性、源文件哈希、CSV/NPZ回读、模型包复现和SVG曲线点位映射检查见 `validation.json`。',
      '', '[方法与运行说明](../README.md) · [来源](../SOURCES.md)','']
    (out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=OUTPUT)
    args=parser.parse_args();out=prepare_output(args.output)
    try:
        import psutil
        proc=psutil.Process();allowed=proc.cpu_affinity();proc.cpu_affinity([allowed[0]])
    except (ImportError,AttributeError):pass
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT/'tests/data_generation/stage/sea_level'),top_level_dir=str(ROOT)))
    tests=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),passed=result.wasSuccessful())
    write_json(out/'tests.json',tests)
    if not tests['passed']:raise SystemExit(1)
    curve=SeaLevelCurve.from_files();age,level,joins=export(curve,out)
    print('Exported 48,001 chronological samples',flush=True)
    figures(curve,out,age,level);validated=verify(curve,out,age,level,tests,joins)
    report(out,curve,validated,joins)
    import scipy,matplotlib
    write_json(out/'manifest.json',dict(version=VERSION,python=sys.version,
        libraries=dict(numpy=np.__version__,scipy=scipy.__version__,matplotlib=matplotlib.__version__),
        code=[dict(path=str(p),sha256=file_hash(p)) for p in CODE.rglob('*') if p.is_file() and out not in p.parents and '__pycache__' not in p.parts],
        output=[dict(path=str(p.relative_to(out)),sha256=file_hash(p)) for p in out.rglob('*') if p.is_file() and p.name!='manifest.json']))
    print('Validation passed:',validated['passed'],'SVG points:',validated['svg']['vertices'],flush=True)


if __name__=='__main__':main()
