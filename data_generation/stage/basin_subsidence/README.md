# 沉降独立事件生成

本模块按当前讨论确认的设计实现：先生成完整成熟期参考场，再生成同一事件的空间时间变化，最后以固定500×500 km窗口查询。A图显示实际网格与节点速率；B至E沿用汇聚的空间图组、固定窗口、生命周期和双时间轴组织。

当前为独立输入模块。输出U单位m/yr，向上为正、向下为负。输入时间为从距今48 Ma起算的年数，模拟终点为48,000,000年。完整活动使用自身公里尺度，自然寿命保留至自然结束，查询与画面截止现代。完整LEM演化继续属于后续管线阶段。

八个固定数据域保留11个独立事件、74个时间画面。2026-09-28重新采样窗口后，19项程序测试、438项产物核查及279个本地链接检查通过；130个受保护文件和11份完整场累计位移与修改前一致。42,240个候选中20,497个通过筛选，窗口采样及查询用时19.57秒。完整场全部位于台地内的本次结果由1个变为3个，逐事件概率和本次结果分别保留。原完整事件生成用时118.84秒、单数据域最长117.75秒，66个核心文件在当时的两次完整生成中哈希一致；这些历史计时与本次采样计时均不包含图集绘制或完整LEM。详细记录见[本轮交付](output/delivery.md)。

## 入口

- [事件图集](output/gallery.html)
- [全部成熟期场](output/overview.png)
- [窗口采样修改前后与概率核对](output/window_sampling_review.html)
- [全部窗口与台地](output/window_sampling_overview.png)
- [四组A至E图](output/four_groups_20260928/gallery.html)，固定种子1001、1004、1005、1006，20张独立图及27个时间画面
- [概率拟合与原始资料](output/model_overview.png)
- [数值与产物核查](output/audit.json)
- [方法、假设与范围](METHOD.md)
- [来源与复用](SOURCES.md)
- [参数依据表](models/parameter_provenance.csv)

在项目已有`lem-env`中运行：

```powershell
& F:\LEM\data_generation\stage\basin_subsidence\run.ps1
```

入口支持`prepare`、`fit`、`generate`、`resample`、`render`、`audit`和`all`。默认种子1001至1008、最多8个工作进程，每个进程绑定独立物理核心，数值库使用一个线程。`render`只读取保存参数和数组并生成展示，不重新抽样。新的试验结果可通过`-Output`写入本模块内另一个目录。

对已保存的整个批次重新采样窗口并更新展示：

```powershell
& F:\LEM\data_generation\stage\basin_subsidence\run.ps1 -Stage resample
& F:\LEM\data_generation\stage\basin_subsidence\run.ps1 -Stage render
& F:\LEM\data_generation\stage\basin_subsidence\run.ps1 -Stage audit
```

`resample`读取目标目录的`batch.json`中所有事件；种子选择沿用该批次。完整场、生命周期和时间数组保持原值，窗口位移使用新的查询坐标计算。全部候选先在`checks/resampling_staging/`保存，各事件均成功后才替换窗口结果。当前几何运算复用项目已有D环境中的Shapely包，具体位置与身份见[METHOD](METHOD.md#窗口与展示)。

集中测试：

```powershell
& F:\LEM\lem-env\python.exe -B -m unittest discover -s F:\LEM\tests\data_generation\stage\basin_subsidence -p 'test_*.py' -v
```

## 查询接口

```python
from data_generation.stage.basin_subsidence.schedule import BasinSchedule, Event

world = BasinSchedule(1001)
u = world.at_time(20_000_000)                 # 500x500, m/yr
dz = world.displacement(20_000_000, 21_000_000)  # m
mean_u = world.mean_rate(20_000_000, 21_000_000) # m/yr

event = Event('F:/LEM/data_generation/stage/basin_subsidence/output/seed1001/event00', layout='complete')
u_full = event.at_time(20_000_000)
# event.x_km, event.y_km give this event's full physical coordinates.
```

所有查询读取已经保存的事件参数，不推进随机数。空间插值权重固定，时间位移在节点上分段积分后使用同一权重查询，支持跨阶段和跨地质世的时间步。

## 展示与产物

每次触发产生独立事件目录：

| 文件 | 内容 |
|---|---|
| `event.json` | 独立事件编号、空间种子、开始时刻、阶段时长、自然寿命 |
| `mesh.npz` | 不规则网格、三角形、节点速率、空间偏好、物理坐标 |
| `reference.npz` | 完整1 km成熟期参考场 |
| `sampling.npz`、`spatial.json` | 抽样轨迹、不同初始状态、目标概率、诊断及尺度映射 |
| `time_model.npz/json` | 固定时间曲线系数、各处启动退出时间及来源身份 |
| `selection.json`、`window.npz` | 500 km刚体窗口、原场查询权重、截取U及粉色交集 |
| `entry_paths.json`、`window_candidates.csv` | 全部穿越轨迹、候选位置、筛选状态、权重分项和抽取概率 |
| `window_diagnostics.png/svg/json` | 候选数量分布、加权概率分布与本次选择 |
| `native_frames.npz`、`frames.json` | E图各时刻实际数组及完整阶段取样比例 |
| `displacement.npz` | 模拟时窗内累计构造位移，单位m |
| `A`至`E`的PNG和SVG | 原尺寸空间图与生命周期图 |
| `traces.png/svg/npz` | 固定位置的速率与累计位移 |
| `summary.json` | 实际范围、速率、累计量、抽样与源数据对照 |

A、B、C使用同一范围与比例尺，D展示固定数据域，E各帧保持该事件完整图幅。全部事件、空间图和时间帧使用同一FEM十二级数值色标。透明处对应零贡献；D图底图与等高线来源保持原始高程，U图层单独显示。粉色表示初始台地与截取作用范围的交集。

A、B、C与E的外框表示绘图范围，C与E的红框表示实际500 km数据域。窗口候选从完整场边界沿160条轨迹穿越，每条24个分层随机位置。台地覆盖范围为10%至70%；完整事件面积不足台地10%时豁免下限，同时要求有实际交集。从50%覆盖开始连续降低覆盖权重。尺寸和进入程度共同降低位置权重，再与面积保留、自然归零边界权重相乘，归一后随机选择。具体定义与设计取值见[METHOD](METHOD.md#窗口与展示)。

阶段标为增强、维持、减弱，描述活动包络。资料约束的局部时间曲线允许内部变化及暂时反向运动。各阶段按完整时长0%、33%、66%、100%取样，零维持跳过，现代截断补一帧。自然结束晚于现代时保留剩余寿命及对应时间比例。

## 数据与当前依据

B07原始回剥卸载构造沉降量及七时段速率提供配对数值约束，已逐列复算。1,818个位置属于同一条测线。B01、B03/B05和B07的阶段记录约束寿命；分世触发使用新整理的沉降启动记录及显式平滑。B03的200 km完整盆地长度用于尺寸中位数参照，尺寸离散程度为设计值。B03/B05已发表的二维图用于理解内部结构，未伪造其原始数值网格。

空间组织、数值边界及二维关联包含设计假设。`summary.json`同时保留实际生成分布与源分布的差异。有限链诊断、代码测试和图像检查具有各自范围，用户验收独立。

初始台地与海底直接只读复用汇聚模块已有的八份数据域，来源哈希在`sources/manifest.json`。既有背景、汇聚和裂谷模块保持原有文件与产物。

## 复现与公开范围

源码使用Python 3.12、NumPy、SciPy、Numba、Matplotlib、Pillow、psutil和Shapely。本机沿用`lem-env`与已有D环境的几何库，绘图使用Microsoft YaHei。`prepare`读取本地参考资料和既有汇聚底图、冻结复用模板，`fit`建立参数包，之后执行生成与绘图；本次文档同步和发布没有安装环境或重新拟合。

公开内容包含生成、拟合、窗口采样、查询与核查源码、专用测试及README、METHOD、SOURCES、WORK_LOG。`sources/` 中的原始资料与冻结模板副本由Git在private跟踪、不公开；其中的数据文件与拟合包、生成产物按忽略规则保留本地，会话、研究和发布记录保留private。公开仓库中的本地资料与图集链接提供路径定位；复现完整生成需准备对应输入。来源与本轮文档发布依据见[项目来源](../../../final-strategy/sources.md#basin-subsidence-20260928)。
