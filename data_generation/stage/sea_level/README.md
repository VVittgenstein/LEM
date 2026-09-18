# 海平面曲线：距今4800万年至现代

2026-09-12，yZz确认数据4与数据1已完成，数据1中的本模块成果纳入本轮验收。原话与收尾范围见 [用户确认](../../../docs/work/2026-09-12-input-stages-closeout/decisions.md#u13)。具体工程方法与资料限制继续保留，后续LEM联调和终态验证按对应阶段推进。

本目录保存本阶段的全部代码、说明和生成结果。使用按年代接续的单一重建曲线；主图横轴为时间、纵轴为海平面。

- [主图SVG](output/sea_level_48ma_to_present.svg)
- [主图PNG预览](output/sea_level_48ma_to_present.png)
- [接点放大SVG](output/junctions.svg)
- [结果与衔接说明](output/REPORT.md)
- [CSV时间表](output/sea_level_48ma_to_present.csv)

## 年代与来源

| 年代范围 | 采用的资料 |
|---|---|
| 距今4800万年至100万年 | Miller等2020年平滑曲线 |
| 距今100万年至98万年 | Miller平滑与未平滑曲线的局部衔接 |
| 距今98万年至79.8万年 | Miller未平滑重建 |
| 距今79.8万年至79.4万年 | Miller未平滑与Spratt曲线的局部衔接 |
| 距今79.4万年至现代 | Spratt与Lisiecki 2016年五记录堆叠曲线 |

历史讨论与本轮要求先后确定：海平面使用一条覆盖距今4800万年至现代的曲线；中间18.2万年的资料间隔由Miller未平滑版补充；保留原始资料、来源及接点处理记录；本轮用户指示将全部工作放在本目录，并附带时间与海平面的SVG图。两处局部窗口、插值方法及核查判据是具体工程实现。

数据来自已经下载的三份文件，读取时保持原样：

```text
F:\LEM\references\data\2026-09-08-q1-data\A\miller2020-smoothed.tab
F:\LEM\references\data\2026-09-08-q1-data\A\miller2020-unsmoothed.tab
F:\LEM\references\data\2026-09-08-q1-data\A\spratt2016-noaa.txt
```

完整文献、数据DOI、原始口径及许可说明见 [SOURCES.md](SOURCES.md)。原文件哈希、覆盖范围、读取列及使用点数写入 `output/sources.json`。未平滑文件在全范围内有重复年代，本模块的桥接及比较区间年代唯一，因此无需合并重复观测；范围外的数据不进入插值。

## 单一曲线的构造

每份资料均换算为BP年和米，按年代升序构造PCHIP插值器，关闭外推。PCHIP保留原始节点值和局部单调性，具有连续一阶导数。

区间内只有对应年代的资料参与。两处接点附近，采用五次平滑权重 `w(u)=6u⁵−15u⁴+10u³`，其中u为重叠区内由较年轻端至较老端的归一化年代。接续值为 `(1−w)×较年轻来源 + w×较老来源`。权重介于0至1，两端的一阶变化率为零，衔接后的海平面及一阶变化率连续。

较老的衔接区固定为98万至100万年前，共2万年，对应Miller平滑数据一个采样间隔。较新的衔接区固定为79.4万至79.8万年前，共4千年。后者比较了1千至2万年的候选窗口，选取未使局部峰值升降速率超过同区间两份原资料峰值的最短窗口。4千年为本批选择结果，全部候选保存在 `window_comparison.json` 和CSV中。

这一选择使较新接点相对于直接切换资料的最大改动由2万年窗口的约52.38 m降至约23.85 m。衔接图同时显示原资料与接续曲线，逐点改动量保存于 `joining_adjustments.csv`。较老接点最大改动约21.22 m。处理方法和窗口属于本项目的局部衔接规则。

原Miller平滑与Spratt曲线的年代覆盖没有交叠；Miller未平滑数据同时覆盖两端附近的年代，局部衔接使用这两处实际重叠。各源发布的年代模型和高程基准保留，本轮没有进行年龄模型校正。源间数值差异的成因没有在本模块中重新估计。

## 时间轴与高程零点

主CSV和NPZ以较老到较新的顺序排列，共48001行，统一导出步距1000年：

| 字段 | 含义 |
|---|---|
| `age_yr_bp` | 距今年代，由48000000递减至0 |
| `time_from_48ma_yr` | 自4800万年前开始经过的时间，由0递增至48000000 |
| `sea_level_m` | 单一曲线的海平面值，沿用原资料相对现代海平面的标称基准 |
| `source_regime` | 当前年代的资料来源或局部衔接类别 |
| 三项`weight_*` | 各来源权重，和为1 |
| `unblended_splice_m` | 在98万年和79.8万年直接切换资料的对照值 |
| `joining_adjustment_m` | 局部接续处理相对上述对照的改动 |
| `rate_forward_m_per_kyr` | 随时间向现代推进的海平面变化率，单位m/千年 |

现代端点保留Spratt重建值8.96 m，原资料在0 BP处的估计值与其标称现代基准有偏差。主曲线未对此作整体平移。模拟截取接口另行减去所选区间的起始值，使模拟初始海平面严格为0 m，从而衔接现有初始海底。

1000年是导出时间间隔。较老段的原资料仍为2万年间隔，并经过滤波以削弱短于约49万年的变化；较新段信息更细。插值没有增加较老时期的原始时间分辨率。Spratt的原始不确定度随模型包保留，本模块没有为整条接续曲线构造新的置信区间。

## 运行与查询

```powershell
& F:\LEM\data_generation\stage\sea_level\run.ps1
```

入口执行测试、读取资料、接续、导出、绘图及回读核查。默认使用既有D会话的隔离Python环境，不安装依赖；`-PythonPath`可指定具有NumPy、SciPy和Matplotlib的已有解释器。结果默认进入本目录的`output`。`-Output`仅允许本目录下的其他子目录，已有非空目录须具有本模块身份标记。重复执行更新该批次同名产物。

在本目录中可以直接使用以下接口：

```python
from sea_curve import SeaLevelCurve

curve = SeaLevelCurve.from_bundle("output/curve_model.json")
sea_level = curve.at_age(800_000)  # 距今80万年的海平面，m

# 从距今500万年开始，按真实年代方向前进200万年。
schedule = curve.window(start_age_yr_bp=5_000_000,
                        duration_yr=2_000_000,
                        step_yr=1_000)
assert schedule["sea_level_m"][0] == 0.0
```

模拟窗口只截取同一条主曲线，超出0至4800万年范围会报错。末个时间点精确包含所请求的模拟终点。该接口不自动选择模拟时长、不随机改变振幅，也不循环或反向复用资料。当前交付为独立数据和查询接口，旧主线代码未在本轮改写。

## 产物与核查

| 文件 | 内容 |
|---|---|
| `sea_level_48ma_to_present.svg` | 矢量主图，时间由左至右推进到现代，纵轴海平面m |
| `sea_level_48ma_to_present.png` | 主图预览 |
| `junctions.svg`、`junctions.png` | 最近120万年及两处衔接放大图 |
| `sea_level_48ma_to_present.csv`、`.npz` | 完整统一时间表、来源权重和改动量 |
| `curve_model.json` | 可独立加载的源节点、固定窗口和方法元数据 |
| `source_points.csv`、`sources.json` | 使用的源节点与原始文件身份 |
| `joining_adjustments.csv`、`junctions.json`、`junctions.csv` | 局部改动、接点原值和连续性检查 |
| `window_comparison.json`、`.csv` | 较新接点的候选窗口比较 |
| `tests.json`、`validation.json`、`manifest.json` | 测试、数据与SVG回读、文件哈希 |
| `REPORT.md` | 本批结果说明 |

SVG保留全部48001个主曲线点，文字转换为矢量路径，显示不依赖外部字体或图片。核查从SVG重新读取曲线坐标，验证时间轴方向及横纵坐标与原数据的线性映射。

六项测试覆盖完整范围、过渡区外原节点值、接点高程及变化率连续、局部凸组合、模拟时间方向与终点、域外拒绝。生成后进一步核查CSV/NPZ回读、模型包数值复现和源文件哈希。衔接规则的工程核查与后续LEM中的地形响应验证分别记录。
