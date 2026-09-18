# 初始海底高程、起伏与等高线

2026-09-12，yZz确认数据4与数据1已完成，数据1中的本模块成果纳入本轮验收。原话与收尾范围见 [用户确认](../../../docs/work/2026-09-12-input-stages-closeout/decisions.md#u13)。具体工程方法与资料限制继续保留，后续LEM联调和终态验证按对应阶段推进。

本目录实现已讨论的初始海底阶段：读取六份已验收的台地mask和深浅海完整分区标签，使用全部种子共用的固定统计参数生成初始水下高程，输出等高线、剖面和起伏检查图。

入口为 `run.ps1`，默认输出为 `output/initial_bathymetry/fixed_profiles_v1/`。本阶段生成500×500、1 km格距的初始高程；后续LEM演化及其验收另外执行。

## 本轮用户要求

本次对话中，用户给出并逐项确认：

- 台地、浅海、深海的基准高程分别为−53、−453、−3746 m，相对初始海平面。
- 台地和浅海的3 km窗口起伏标准差目标为2.0 m，深海为8.3 m。
- 坡折宽度指台地边缘到开始转入陡坡的位置，前段为缓坡。浅海、深海方向分别采用统计中的固定平均宽度、坡折深度及坡折后20 km内的代表坡度，各种子共用。
- 深浅海交界附近的高程和坡度平滑衔接，具体方法依据现有参数实现，并通过高程图和剖面图检查。
- 空间不足时保留既定宽度和坡度，只计算数据域覆盖的部分。
- 起伏使用简单的空间相关随机场，空间尺度依据已有统计固定，各种子只改变具体分布；首轮后结合LEM结果检查影响。
- 新增代码放置于 `F:\LEM\data_generation\stage\initial_bathymetry`，以等高线输出图。用户在确认这些要求后明确指示“可以开始”。

下面的平均权重、曲线公式、1 km距离正则化、交界混合函数和短尺度随机场拟合是具体工程实现。它们与用户要求分别说明，当前成果的验收状态见本文开头，计算核查继续作为对应范围的工程证据。

## 输入与复用

| 输入 | 位置与含义 |
|---|---|
| 六份mask和512分区 | `output/mask_generator/world_orogen_gibbs_layers_3/partitions_512/seed1001`至`seed1006`，外围3层禁选 |
| 已验收海域标签 | `output/seafloor_generator/mean_distance_v1/seed*/seafloor_type.npy`及`region_types.npy` |
| 分类距离 | 已验收海域阶段的`distance.json`，采用95 km |
| 参考总体 | F会话`reference-cohort.json`中纬度绝对值小于60°的34个陆块 |
| 坡折与坡度观测 | `references/data/2026-09-09-q1-pretasks/F/stations/*.npz`中的冻结剖面 |
| 起伏窗口统计 | A会话`tables/spatial-quantiles.csv`，筛选相同34个陆块 |

只读复用 `mask_generator/common/io.py`、既有几何计算和 `seafloor_generator/coast.py` 的输入读取与校验。没有重抽mask、重分海域或修改原批次文件。原海域类型标签在融合高程之后仍完整保留为输入记录；实际海底高程在类型边界附近连续变化。

历史取证入口：

- [67775e98原始讨论](../../../docs/sessions/2026-09-07-lem-continent-generation-methods-67775e98/conversation.md)
- [639e9e4e讨论与执行](../../../docs/sessions/2026-09-09-lem-pipeline-execution-marine-recovery-639e9e4e/conversation.md)
- [dc2cbd65形状选择](../../../docs/sessions/2026-09-11-lem-platform-shape-selection-dc2cbd65/conversation.md)
- [本轮之前的海域分配实现](../seafloor_generator/README.md)

## 固定参数与数据口径

在原F剖面95 km端点，以类别1、3、4作为浅海，类别2作为深海；未知、地壳分歧及非海水端点单列。每类只用宽度、坡折深度、坡度三项均有效且为正的同一组站点。先在各陆块内取算术平均，再对有有效观测的陆块等权平均，全部种子共用结果。

| 方向 | 坡折宽度 km | 坡折水深 m | 坡折后坡度 m/m | 每公里下降 m | 有效陆块 | 有效站点 |
|---|---:|---:|---:|---:|---:|---:|
| 浅海 | 80.901820 | 197.435400 | 0.078593658 | 78.593658 | 24 | 8950 |
| 深海 | 17.774072 | 281.261095 | 0.153215152 | 153.215152 | 11 | 2207 |

原F的宽度为首次陆架转入陆坡的法向距离，坡折水深为该陆坡侧采样点的水深。坡度为其后20 km内有效陆坡格的二维梯度模均值；本轮按照已讨论的简化，用它表示固定剖面的陡坡坡度。20 km为测量范围，陡坡实际长度由剩余高差及坡度决定。

宽度只记录在250 km内遇阻前能够找到的转换；缺测不填零，不以250 km替代。浅海、深海有效站点中具有完整20 km观察窗口的分别为8641和2200个，其余窗口的可观察长度较短。逐陆块均值、有效数和缺测数保存于 `reference/profile_means.json` 与CSV。

来源：[F-004测量定义](../../../docs/work/2026-09-09-q1-pretasks/F-periphery-150km/records/F-004-shelf-profiles.md)、[F脚本说明](../../../docs/work/2026-09-09-q1-pretasks/F-periphery-150km/scripts/README.md)。真实海岸测量值用于初始水下台地边缘，属于本项目的构造用法。

## 剖面与二维衔接

`profiles.py`先用正水深计算，写入数组时改为负高程。坡折宽度为W、坡折水深为B，台地水深为53 m。在0至W内，使用归一化距离t=d/W和曲线 `2t²−t³`，使水深从53 m增加至B。台地端的基础坡度为零，坡折前平均坡度为 `(B−53)/(1000W)`，最大缓坡坡度为该平均值的4/3。

从W开始，将缓坡末端坡度平滑接到原统计陡坡坡度，随后保留一段固定陡坡，最后平滑接入目标底面。连接处高程与一阶导数连续。连接长度不超过3 km，同时由W和剩余高差限定，全部种子共用；完整公式与派生值位于 `Profile.depth()` 和 `parameters.json`。

加入平滑连接后，浅海、深海分别在距离台地边缘 **85.760934 km、42.090542 km** 处到达目标底面。这些距离由固定参数计算，不依赖某个样本的可用空间。

二维表面使用每个格点至最近台地的距离。按1 km格网计算中心距离并减去半格，再作固定1 km高斯正则化以平滑小尺度距离折线；台地内部基础高程保持−53 m。距离正则化误差单列于各样本统计。

深浅海交界使用两个固定剖面在当地的高差确定混合带总宽度：`max(3 km, 1.875 × 高差 / 深海陡坡坡度)`，长度单位在代码中统一为km。沿类型边界的平滑有符号距离使用五次平滑函数 `6t⁵−15t⁴+10t³` 形成权重，再对两类基础高程作连续加权。1.875来自该函数导数的最大值，3 km为1 km格网上的最低平滑范围，是工程实现参数。

在外部留有计算边带，完成距离和平滑后才裁取500 km数据域，避免把域边界处理成额外坡脚。窄海湾和内部空缺使用当地最近台地距离，可能无法达到坡折或目标底面。狭窄深海分区的两侧混合带也可能相互影响。固定参数控制基础剖面，实际二维坡度还随轮廓和混合权重变化；原图、剖面图及混合权重数组全部保存。

## 简单空间相关起伏

采用零均值高斯白噪声，经高斯空间滤波得到连续凸起和凹陷。先对具有3、5、10 km窗口观测的每个陆块计算5/3和10/3的局部标准差比，再对陆块等权平均；用一个固定校准随机场拟合滤波尺度。

| 类别 | 参考陆块 | 高斯滤波尺度 | 3 km窗口标准差目标 |
|---|---:|---|---:|
| 台地、浅海 | 27 | 约2.900 km，精确值见参数文件 | 2.0 m |
| 深海 | 17 | 约4.015 km，精确值见参数文件 | 8.3 m |

台地与浅海共用相关场和参数，深海使用另一独立相关场。各随机实现归一化至共同的局部标准差目标，再按类型和到台地的距离平滑混合；台地边缘保持共同的2 m起伏场，深海方向的起伏强度在缓坡范围内逐渐增大。归一化系数记录为随机实现的处理结果，物理目标值和空间尺度始终固定。

3 km窗口为3×3个格子的总体标准差。统计对象是扣除基础剖面后的起伏，按区域内部窗口的标准差中位数核查；交界处起伏强度连续变化，混合带和各类型全部窗口的统计另存。窗口均值可随空间变化，因此整个区域的起伏范围也单独记录。

本轮拟合短尺度比，25、50、100 km资料保留作参考，未声称匹配全部尺度。原GEBCO起伏含测线覆盖、插值及地形趋势的影响，单一高斯协方差是首轮简化。来源：[A-016](../../../docs/work/2026-09-08-q1-data/A-initial-elevation-sealevel/records/A-016-shelf-roughness.md)、[A-017](../../../docs/work/2026-09-08-q1-data/A-initial-elevation-sealevel/records/A-017-oceanic-roughness.md)。

## 运行

```powershell
& F:\LEM\data_generation\stage\initial_bathymetry\run.ps1
& F:\LEM\data_generation\stage\initial_bathymetry\run.ps1 -Stage prepare
& F:\LEM\data_generation\stage\initial_bathymetry\run.ps1 -Stage generate
& F:\LEM\data_generation\stage\initial_bathymetry\run.ps1 -Stage audit
& F:\LEM\data_generation\stage\initial_bathymetry\run.ps1 -Stage test
& F:\LEM\data_generation\stage\initial_bathymetry\run.ps1 -Stage render
```

`all`依次测试、重算固定参数、生成六份数据与图片、回读复现并写入清单。`generate`使用已经准备的固定参数，并核查参考输入哈希。`audit`重新生成数组作固定种子复现，检查保存数据及等高线坐标。

`render`只读取已有数组重绘六张主图及总览，更新查看页和显示坐标，不重新生成地形。台地内部保留等高线，外侧只画四类红线；颜色按台地边缘、坡折线、坡脚线、深浅海分区边界的顺序由深到浅。背景连续颜色表示实际高程。坡折、坡脚分别按原分区类型的固定宽度与坡脚距离，在距离场中取线，融合区域中的这些线属于参数参考位置。深浅海分区边界来自已验收的原标签。重绘前后检查全部数组、固定参数和剖面文件哈希一致。

默认使用既有D会话的隔离Python环境，不安装依赖；可用 `-PythonPath` 指定具有NumPy、SciPy、Shapely、Pillow、Matplotlib的已有环境。执行为一个进程，数值线程设为1，可用时将该进程固定到一个CPU。`-Output`可以另存一批。程序拒绝与输入或代码目录重叠的输出路径，已有非空输出须有本程序的身份标记。

## 文件与核查

| 产物 | 内容 |
|---|---|
| `comparison_contours.png` | 六种子等高线总览，使用相同等高线级别与色标 |
| `fixed_profiles.png` | 两种固定一维剖面，标注坡折位置、深度和陡坡坡度 |
| `seed*/contours.png` | 台地内部等高线与台地外四类红色分界线 |
| `seed*/boundary_lines.json`、`rendering_checks.json` | 四类显示线坐标、定义及重绘回读与数据不变检查 |
| `seed*/profiles.png`、`sections.json` | 东西、南北及两条海侧测线，保存坐标和数值；记录选线规则和终点含义 |
| `seed*/roughness.png` | 起伏等高线与3 km窗口统计 |
| `seed*/elevation.npy` | 最终初始高程，float64，单位m |
| `seed*/base_elevation.npy`、`roughness.npy` | 基础高程与叠加起伏，两者之和等于最终高程 |
| `seed*/distance_km.npy`、`raw_distance_km.npy` | 正则化与原始格网距离，单位km |
| `seed*/deep_weight.npy`、`noise_deep_weight.npy` | 高程与起伏的连续混合权重 |
| `seed*/shallow_profile.npy`、`deep_profile.npy` | 两类固定剖面在相同距离场上的候选高程 |
| `seed*/shallow_unit_noise.npy`、`deep_unit_noise.npy` | 用于独立核查的归一化相关场 |
| `seed*/contour_lines.json` | 加等高线标签前导出的真实等值线坐标，局部平面km坐标 |
| `parameters.json`、`reference/` | 固定参数、平均与拟合方法、逐陆块数据、来源哈希 |
| `metrics.json`、`audit.json`、`tests.json`、`manifest.json` | 数值、起伏、截取、交界、复现与文件身份核查 |
| `report.html`、`REPORT.md` | 查看入口与结果说明 |

数组第0行位于图的下方；格心坐标为0.5至499.5 km，x向右、y向上。图中高程相对初始海平面0 m，水下为负。色标采用对称对数归一化，以同时显示数十米与数千米高差，刻度给出实际米值。

测试覆盖固定剖面的单调性和参考点、一阶导数连续性、截取保持参数、二维计算边界不压缩剖面、交界混合函数及相关场复现。交付检查读取实际数组，核对全域水下、台地基础高程、分量相加、原标签与来源哈希、固定种子复现，以及导出等值线顶点在保存高程上的插值值。区域内部起伏中位数采用12%的工程检查容差，实际偏差逐项公开。LEM影响和地学合理性检验保留为后续阶段。
