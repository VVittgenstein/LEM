"""Assemble the first-round review from saved, inspectable evidence."""
from __future__ import annotations
import contextlib
import io
import json
import re
import sys
from pathlib import Path
from workspace import PROJECT, ROOT, digest, read_csv, target, utc_now, write_csv, write_json

def code_review():
    files={
        'data_generation/stage/convergent_uplift/time_pipeline/schedule.py':['active=reference>0','def at_time','def displacement','def mean_rate'],
        'data_generation/stage/convergent_uplift/time_pipeline/timing.py':['hazard','epoch'],
        'experiments/lem_pipeline/driver.py':['(self.nx - 1)','def set_uplift','fastscape_set_u'],
        'pyproject.toml':['testpaths'],
        'data_generation/pipeline/README.md':['stage'],
    }
    results=[]
    for relative,patterns in files.items():
        source=PROJECT/relative
        lines=source.read_text(encoding='utf-8').splitlines()
        results.append(dict(path=relative,sha256=digest(source),
            matches=[dict(line=i+1,text=line) for i,line in enumerate(lines) if any(p in line for p in patterns)]))
    write_json('output/checks/code_review.json',results)

def notebook():
    cells=[]
    def markdown(text):cells.append(dict(cell_type='markdown',metadata={},source=text.splitlines(keepends=True)))
    def code(text):cells.append(dict(cell_type='code',metadata={},source=text.splitlines(keepends=True),execution_count=None,outputs=[]))
    markdown('# 裂谷第一轮核验\n\n原件只读。所有计算对应本目录冻结资料。这里重算关键记录数、资料异常和运动约束；完整扫描脚本位于 scripts。测试输入不具有天然参数身份。\n')
    code("from pathlib import Path\nimport csv, json, zipfile, hashlib, sys\nsys.dont_write_bytecode = True\nroot = Path.cwd()\nif root.name == 'notebooks': root = root.parent\nif not (root/'sources').exists(): root = root/'data_generation/stage/rifting'\nassert (root/'sources').exists()\ndef csv_rows(path):\n    with path.open(encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))\n")
    code("wsm = csv_rows(root/'sources/new/N01/WSM_Database_2025.csv')\nabc = [r for r in wsm if r['QUALITY'] in ['A','B','C']]\nnf = [r for r in abc if r['REGIME']=='NF']\nprint({'WSM':len(wsm),'A-C':len(abc),'A-C NF':len(nf),'NF FMS':sum(r['TYPE']=='FMS' for r in nf)})\nassert len(wsm)==100842 and len(nf)==22154\n")
    code("with zipfile.ZipFile(root/'sources/new/N03/fault_statistics.zip') as z:\n    prefix='Extracted fault statistics/Geometric_relationships/Appended_relationships_Model'\n    b,e=z.read(prefix+'B.xlsx'),z.read(prefix+'E.xlsx')\nprint({'B_E_equal_bytes':b==e,'sha256':hashlib.sha256(b).hexdigest()})\nassert b==e\nfaults=json.loads((root/'sources/new/N02/MSSM_faults.geojson').read_text(encoding='utf-8'))['features']\nbad=[f['properties']['MSSM_id'] for f in faults if f['properties']['dip_lower']>f['properties']['dip_int']]\nprint({'MSSM_faults':len(faults),'dip_order_failure_ids':bad})\nassert bad==['316']\n")
    code("import numpy as np\nA=np.array([[-1.,1,0],[0,1,-1]])\nd=np.array([-1.,-1.])\nM=np.vstack([A,[.5,0,.5]])\nu=np.linalg.solve(M,np.r_[d,0.])\nprint({'relative_constraint_rank':int(np.linalg.matrix_rank(A)),'unknowns':3,'velocities_mm_per_yr':u.tolist()})\nassert np.allclose(u,[0,-1,0])\n")
    markdown('## 计算范围\n\n上面的块体例子检查相对约束、参考基准及共同中央状态。二维有限元完整检查见 scripts/method_checks.py 和 output/checks/method_checks.json。长期响应、三维断层生成与完整LEM尚未验证。\n')
    book=dict(cells=cells,metadata=dict(kernelspec=dict(display_name='Python 3',language='python',name='python3'),language_info=dict(name='python',version=sys.version.split()[0])),nbformat=4,nbformat_minor=5)
    # Execute the authored plain-Python cells and save their actual outputs.
    import os
    old=Path.cwd();namespace={};count=0
    try:
        os.chdir(ROOT)
        for cell in cells:
            if cell['cell_type']=='code':
                count+=1;stream=io.StringIO()
                with contextlib.redirect_stdout(stream):exec(compile(''.join(cell['source']),'evidence_review.ipynb','exec'),namespace)
                cell['execution_count']=count
                cell['outputs']=[dict(output_type='stream',name='stdout',text=stream.getvalue().splitlines(keepends=True))] if stream.getvalue() else []
    finally:os.chdir(old)
    write_json('notebooks/evidence_review.ipynb',book)

def main():
    p=json.loads((ROOT/'output/checks/source_profiles.json').read_text(encoding='utf-8'))
    q=json.loads((ROOT/'output/checks/quality_findings.json').read_text(encoding='utf-8'))
    m=json.loads((ROOT/'output/checks/method_checks.json').read_text(encoding='utf-8'))
    w=p['csv']['WSM2025'];gem=p['geo']['GEM'];malawi=p['geo']['MSSM']
    magnitude=json.loads((ROOT/'output/checks/Germany_magnitude_profile.json').read_text(encoding='utf-8'))
    rows=read_csv(ROOT/'output/tables/Germany_stress_magnitudes.csv')
    mac=sum(r['QUALITY'] in ['A','B','C'] for r in rows)
    m_nf=sum(r['QUALITY'] in ['A','B','C'] and r['REG']=='NF' for r in rows)
    report=f'''# 裂谷资料与方法第一轮核验

状态：本轮核验已执行，生成模块尚未实现或验收。

## 本轮判断

现有资料支持开始部分统计处理与分层数值原型。完整的“作用条件到断层概率”和“断层到长期U”定量关系仍需建立。用户确定的两次概率生成及确定性场计算顺序保持。

第一层有现代应力方位和区域应力量值资料，可以用于方向、深度及量级的条件核对。外围与局部作用的数量、接触尺寸和生命周期尚未取得覆盖本方案的联合总体。

第二层有断层几何、网络、分期和速率资料，但包含测量、推算、模拟及重复时刻。本轮确认的字段问题需要在拟合前处理。共同应力如何改变出生概率、增长和长期速率仍需单独校准。

第三层已经完成有限范围的数学与数值检查。绝对运动基准、三维几何、周围形变和长期响应仍待核验。两组算例通过不构成完整地学或LEM验证。

## 数据范围

| 数据 | 实际检查范围 | 当前可用含义 |
|---|---:|---|
| WSM 2025 | {w['rows']:,}行、40字段；A至C级{w['abc_count']:,}条，其中NF {w['abc_normal_fault_regime_count']:,}条 | SHmax方位和应力状态；单震源机制占A至C级NF的{q['WSM']['abc_nf_fms_fraction']:.2%}，配对研究须处理共源依赖 |
| 德国及邻区应力量值 | {magnitude['rows']}行、73字段；A至C级{mac}条，其中NF {m_nf}条 | 区域及深度相关的量值，原单位MPa；不能直接推定全局施力源总体 |
| GEM冻结全库 | {gem['all_features']:,}要素；normal标签筛选{gem['rows']:,}要素 | 保留混合运动；以原要素序号定位；不能按地图要素数计算独立地质活动数 |
| Malawi冻结版本 | {malawi['faults']['rows']}断层、{malawi['sections']['rows']}分段、{malawi['multifaults']['rows']}多断层破裂表示 | 三种层级分别处理，速率保留模型分配身份 |
| Pan补充包 | 23个工作簿；5组数值模型及3个天然对照文件 | 逐表检查维度与字段，天然和模拟分开；重复时刻不计为独立事件 |
| 既有裂谷目录 | 657条；643条原表尺寸限定仍待回查 | 区域构造尺度线索；目录年代不直接提供完整寿命 |
| 北康分期速率 | 10条断层、29条分期记录，差分复算最大误差0 | 两盘地层厚度差速率；保留相对量与原时窗 |

范围与原始入口见 [来源登记](SOURCES.md)，字段覆盖与原始行检查见 [source_profiles.json](output/checks/source_profiles.json)。

## 已确认的数据问题

1. **Pan的Model B与Model E几何工作簿逐字节相同。** 两者SHA-256均为 `{q['Pan_B_E']['sha256_B']}`。原因未查明。这两个文件不能作为两个独立模型分组进入比较。
2. **Pan的Model B时间存在来源差异。** 工作簿age最大20 Myr，代码采用timestep/2.5；补充PDF第12页写1.25 mm/yr模型最终输出10 Myr。原因未查明。该时间列暂不用于寿命拟合。
3. **Pan天然对照中的dip列语义待核对。** 147行中136个值大于90度，范围69.29至347.15。该列暂不作为倾角数据，也不自动改称倾向。
4. **Malawi倾角区间顺序冲突。** 断层316及其分段56、57、82、87的三值为54、53、65度，无法直接作为有序区间抽样。原因未查明。原值保留，相关字段暂不参与拟合。README的部分字段和默认值说明与实际版本存在差异，实际键为MSSM_id。
5. **GEM存在层级与缺失限制。** 正断层筛选中平均倾角缺失{gem['missing']['average_dip']:,}条，下界深度缺失{gem['missing']['lower_seis_depth']:,}条；catalog_id有重复，不能直接作为唯一要素键。
6. **旧裂谷目录的原表限定尚不完整。** 除643条限定未回查外，另有2条宽度为0；原量含义核对前不把0当作天然宽度。首14条原表核对图已检查，确认最大值、上界与群体平均等限定需要保留。

WSM的170条空坐标记录全部为Xmi质量，11,095条AZI=999按技术报告表示无可用方位。本轮保留缺失身份，不将其作为地理位置或角度参与计算。

逐项证据和处理范围见 [quality_findings.json](output/checks/quality_findings.json)。这些问题限定到对应记录、列或文件；其他资料可以按各自证据继续处理。

## 方法检查结果

| 检查 | 实际结果 | 适用范围 |
|---|---|---|
| 静态弹性解析应力 | 8、16、32格网三种离散均通过，最大应力误差{max(x['max_stress_error'] for x in m['mechanics']['affine_patch_cases']):.3g} | 本轮无量纲二维平面应力计算 |
| 远端与局部线性组合 | 最大误差{m['mechanics']['superposition_max_error']:.3g} | 固定线性介质与相同边界 |
| 窗外局部影响 | 中心窗口应力均方根非零；不平衡输入被拒绝 | 本算例局部源位置与平衡记账 |
| 共享岩体和参考基准 | 2个相对约束对3个速度未知量留1个自由度；加入参考后确定中央速度 | 三块体垂向运动学例子 |
| 不相容候选 | 矛盾约束产生0.1667 mm/yr残差并被检查拒绝 | 所声明测试容差 |
| 累计量与确定性 | 分段积分误差{m['kinematics']['partition_integral_error_m']:.3g} m；重复求解一致 | 固定几何及合成连续时间函数 |

检查代码、输入身份及未覆盖项见 [方法核验](METHOD_REVIEW.md)。本轮未运行完整Fastscape、训练或180秒性能测试。

## 下一阶段

建议推进三项有明确输入输出的工作：

1. 建立P1的固定三维参考域，保留外围与全域局部作用、显式反作用、分开的应力贡献及同一历程的固定窗口。对距离、布局、网格与域尺寸做可区分的对照。尺寸和幅值先标明数值试验身份。
2. 用WSM的分组方位和区域量值资料校准可支持的部分，同时整理实际断层几何；对作用数量与时间先验保留独立依据记录，不将它们标为天然拟合。
3. 优先补足条件断层和长期响应的关键资料及参考计算。先处理本轮发现的模型分组、时间和字段问题，再扩大概率拟合。

完整逐参数对应表见 [PARAMETER_EVIDENCE.md](PARAMETER_EVIDENCE.md)，具体缺口见 [GAPS.md](GAPS.md)。

## 复现与边界

本轮所有新增工作保存在本目录，原始资料和其他项目文件未修改。使用现有LEM Python与Codex文档Python环境，未安装新依赖、执行外部作者代码或发布。

已执行的计算过程及关键核验单元见 [可复核Notebook](notebooks/evidence_review.ipynb)。入口说明见 [README.md](README.md)。生成参数只服务数据生产，尚未写入模型训练或推理接口。
'''
    target('REPORT.md').write_text(report,encoding='utf-8')
    # Machine-readable coverage table, derived exactly from the authored review table.
    table=[]
    for line in (ROOT/'PARAMETER_EVIDENCE.md').read_text(encoding='utf-8').splitlines():
        if re.match(r'^\| [FGUI]\d\d \|',line):
            values=[v.strip() for v in line.strip('|').split('|')]
            table.append(dict(id=values[0],parameter=values[1],unit_or_identity=values[2],evidence=values[3],next_action=values[4]))
    write_csv('output/tables/parameter_evidence.csv',table)
    code_review();notebook()
    write_json('output/checks/delivery_build.json',dict(created_utc=utc_now(),parameter_rows=len(table),notebook_code_cells_executed=4))
    print('Built REPORT.md, parameter table, code review and executed notebook.')

if __name__=='__main__':main()
