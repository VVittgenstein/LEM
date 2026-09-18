# 初始海底：深浅海比例与完整地块分配

2026-09-12，yZz确认数据4与数据1已完成，数据1中的本模块成果纳入本轮验收。原话与收尾范围见 [用户确认](../../../docs/work/2026-09-12-input-stages-closeout/decisions.md#u13)。具体工程方法与资料限制继续保留，后续LEM联调和终态验证按对应阶段推进。

本目录实现第一类数据中第4项“比例”和第5项“分配”的阶段程序，输入为已选定的水下台地 mask 与完整分区，输出为台地、浅海、深海三类标签。主入口为 `run.ps1`，六种子交付为 `output/seafloor_generator/mean_distance_v1/`。

当前数组为500×500，格距1 km。标签0为台地 mask，1为浅海，2为深海。本模块交付海域标签；对应高程、起伏与过渡已由 [initial_bathymetry](../initial_bathymetry/README.md) 提供，后续LEM演化单独推进。

## 本轮要求与实现归属

本轮用户明确要求四个拟合函数分别生成周边类型、混合样本的比例、深海段长、浅海段长，再通过组合 mask 管线已有的完整地块近似满足目标；生成时使用拟合函数的新随机数。用户要求用平均值重算观测距离，并确认深海深蓝、浅海浅蓝、mask 灰色。六个种子沿用已选 mask 批次的1001至1006。

下面的测宽细节、分布族、缺测处理、闭合处理和优化权重是本轮 Agent 的具体实现。计算与技术核查记录用于检查结果；它们保持工程实现归属，当前成果的验收状态见本文开头。

| 对象 | 本轮具体实现 |
|---|---|
| 统一观测距离 | 先计算每份 mask 外轮廓的平均可用海域宽度，再对六份均值取算术平均，取最近整数公里 |
| 周边类型函数 | 34个陆块等权拟合的分类概率，使用新的均匀随机数生成类型 |
| 混合比例函数 | 混合陆块的深海沿岸占比，拟合 Beta 分布 |
| 两个段长函数 | 对数正态分布；每个贡献观测的陆块具有相同总权重；完整段用密度，截断段用超过观测下界的概率 |
| 多个台地主体 | 汇总全部外轮廓长度，共用一次类型和比例抽样；目标序列按外轮廓顺序放置，各闭合轮廓分别计段 |
| 内部空缺 | 保留几何形状；外轮廓比例不含内部孔洞边界；没有外岸来源的海域地块首版标为浅海并单列 |
| 位置与完整地块 | 固定生成的类型、比例及段长，比较32个沿轮廓等距位置；每个位置通过整数优化选择完整地块 |
| 向外围延伸 | 在海域地块的共享边界邻接图上，按地块质心间距离寻找最近沿岸来源，继承其类型 |

## 输入与复用

1. 已选 mask：`output/mask_generator/world_orogen_gibbs_layers_3/partitions_512/seed1001` 至 `seed1006`。读取 `mask.npy`、`partitions.npy`、`contours.json`、`config.json`。校验512分区、外围3层禁选、1 km格距和整块台地选择。
2. 参考总体：`docs/work/2026-09-09-q1-pretasks/F-periphery-150km/scripts/reference-cohort.json` 中纬度绝对值小于60°的34个陆块。
3. 参考数据：`references/data/2026-09-09-q1-pretasks/F/stations/*.npz`，读取原F程序保存的1至250 km逐公里剖面。参考站点与原始数据均只读。
4. 复用代码：`data_generation/stage/mask_generator/common/io.py`、`common/render.py` 和 `world_orogen_gibbs/geometry.py`。后者继续使用既有分区数据结构及邻接计算。本程序读取现有分区，不重新运行分区生长或 Gibbs 选择。

新增计算代码、测试、启动脚本与说明全部位于本目录。默认使用已有D会话隔离环境，不安装依赖。一次执行为单进程，数值库线程数设为1；可用时将该进程固定在一个CPU。实际Python及库版本写入产物清单。

历史讨论取证入口：

- [67775e98原始讨论](../../../docs/sessions/2026-09-07-lem-continent-generation-methods-67775e98/conversation.md)
- [639e9e4e讨论及执行](../../../docs/sessions/2026-09-09-lem-pipeline-execution-marine-recovery-639e9e4e/conversation.md)
- [dc2cbd65形状选择支线](../../../docs/sessions/2026-09-11-lem-platform-shape-selection-dc2cbd65/conversation.md)
- [当前 mask 选定配置](../mask_generator/world_orogen_gibbs/SELECTED_PROFILE.md)

历史中的150 km统计保留原样。本程序将新口径结果另存于自己的输出目录。

## 计算顺序与口径

### 1. 测量平均宽度

在每个外轮廓的1 km格边中点向海外测量。方向来自五个连续格边中点的首尾连线，沿岸跨度4 km；如果首个海侧探测点落入台地，退回该格边的准确外法线。射线遇到另一个台地边缘或数据域边界时停止，射线采样步长0.5 km。内部孔洞边界不参与平均。

每个站点代表1 km外轮廓；先对每份样本取平均，再对六份样本均值等权平均。该定义包含海湾内受其他台地部分限制的宽度。

本批六份均值为88.008、106.107、89.330、100.881、95.809、90.732 km，合并均值为 **95.144604 km**。参考剖面间隔为1 km，因此统一观测距离采用 **95 km**。宽度、方向、终止原因和输入哈希保存在 `distance.json` 与 `distance/seed*/measurement.npz`。

此距离用于确定自然参考资料的海侧观测位置；生成图中的海域仍由现有 mask 和完整地块确定。三个禁用层已经体现在输入 mask 中。

### 2. 用95 km端点重算参考统计

沿用F数据的地质与地貌分类分组：

| F类别 | 二元分类 |
|---|---|
| 1 shelf_continental、3 continental_non_shelf、4 transitional | 浅海 |
| 2 oceanic | 深海 |
| 0 unknown、5 crust_disagreement、9 land_or_no_marine | 未知或非海水端点，单列 |

上述“深浅”是本轮沿用的类别名称，尚未指定以多少米水深作为分界。比例分母为可确定深浅类型的海水端点所对应的沿岸长度，同时保留全部沿岸长度作分母的对照值。陆块的“全浅海”表示其已知海水端点均为浅海，未观测部分仍然未知。

95 km重算结果为23个全浅海、11个混合、0个全深海；平均已知端点岸长覆盖率73.82%。全深海的拟合概率为0，这是本参考总体的观测结果。

按原站点顺序识别闭合岸线上的连续二元段，沿用10 km短段合并规则：只有相邻两侧均为已知类别时才合并。未知段始终保留为间隔。触及未知间隔的已知长度作为真实段长的下界，完整长度单列。段长函数使用混合陆块的观测，全浅海轮廓在生成时直接保留整圈。

### 3. 拟合四个函数

`models.FittedFunctions` 提供 `environment(rng)`、`mixed_deep_fraction(rng)`、`deep_length(rng, size)`、`shallow_length(rng, size)`。

| 函数 | 本批拟合结果 |
|---|---|
| 周边类型 | 全浅海23/34，混合11/34，全深海0/34 |
| 混合深海比例 | Beta：alpha=0.560273，beta=1.300858，11个陆块 |
| 深海长度 | lognormal：自然对数均值4.139859、标准差1.059044，长度单位km |
| 浅海长度 | lognormal：自然对数均值4.676845、标准差1.027285，长度单位km |

深海拟合包含34条完整长度与48条下界，来自8个陆块；浅海拟合包含14条完整长度与844条下界，来自11个陆块。每个贡献陆块具有相同总权重，同一陆块内各观测均分该权重。

**数据限制：浅海完整段观测较少。** 拟合依赖所选分布族与截断解释；同一个真实段可能被多个未知间隔分成多条下界，观测间依赖和向生成尺度的转移尚未验证。当前函数属于可执行的阶段拟合，不据此宣称已经复现自然段长分布。

### 4. 生成一组比例与段长目标

种子通过独立随机流生成类型、比例、段长和初始位置。混合样本从两个段长函数生成新的交替段长；比较候选段数与新随机段长，使两类长度分别缩放至总轮廓长及比例目标时的对数缩放量尽量小。候选上限和每种段数的8次提议固定写在 `create_targets()` 中。

保存原始函数输出、缩放系数、闭合后的长度和随机位置。闭合后的长度受到总周长和比例的共同约束，因此与未经约束的单独段长函数有差别。多个外轮廓各自闭合时可能增加段数；目标与结果均按同一实际轮廓测量。

### 5. 按完整地块近似拟合

每个接触台地外轮廓的海域地块只有一个深浅标签，所有格子共同改变。SciPy `milp`求解沿岸目标不一致、比例绝对误差和类型转换误差的加权目标，权重分别为1、5、0.20。沿岸不一致项一半按岸长加权，一半让各目标段等权，减少短段被忽略的情况。

同一组目标序列比较32个等距旋转位置，不重新抽取类型、比例或段长。位置评分为两类比例相对误差的均值，加0.25倍两类归一化段长分布误差之和，再加0.25倍两类段数相对误差之和。段长分布误差使用一阶Wasserstein距离除以对应目标平均段长。

该搜索给出所比较位置中的最小评分，未证明全部可能地块分配的全局最优性。比例误差、段数及段长误差全部保留，用户尚未规定它们的验收阈值。

邻岸标签确定后，在未选中地块的邻接图上向外围传播。同一类型可以占据多个完整地块，全部原分区边界保持不变。内部没有外岸来源的空缺首版设为浅海，其地块编号、面积和实现假设写入 `metrics.json`。

## 运行与检查

```powershell
& F:\LEM\data_generation\stage\seafloor_generator\run.ps1
& F:\LEM\data_generation\stage\seafloor_generator\run.ps1 -Stage prepare
& F:\LEM\data_generation\stage\seafloor_generator\run.ps1 -Stage generate
& F:\LEM\data_generation\stage\seafloor_generator\run.ps1 -Stage audit
& F:\LEM\data_generation\stage\seafloor_generator\run.ps1 -Stage test
```

`all`依次执行测试、测宽、参考重算、函数拟合、六种子生成、图片、回读核查和清单。`-Output`可另存一批，`-PythonPath`可指定具有NumPy、SciPy、Shapely、Pillow和Matplotlib的现有Python。默认解释器为既有D会话的 `.venv/Scripts/python.exe`。

重复执行覆盖本程序输出目录中的同名产物。目录身份标记为 `.seafloor_generator.json`，既有其他非空目录会被拒绝。程序拒绝输出目录与参考数据、mask输入或被复用代码重叠。生成前检查测宽所用 mask 和已准备参考统计的哈希；数据改变后须重新运行 `prepare`。

检查包括人工方形的周长和200 km海宽、闭合段跨起点合并、未知间隔保留、短段合并、完整地块冲突及拟合随机数复现。交付回读检查500×500数组、完整分区一致性、原mask一致性、沿岸比例、段长总和、参考站点数量、来源哈希和PNG逐像素颜色。固定六种子复现记录为 `reproducibility.json`。

## 产物

| 文件 | 内容 |
|---|---|
| `comparison.png`、`report.html`、`REPORT.md` | 六种子总览、原图及阶段图入口、结果与数据限制 |
| `distance.json`、`distance/` | 六样本测宽及95 km口径依据 |
| `reference/`、`functions.json`、`fitted_functions.png` | 重算自然参考、来源哈希、四个拟合函数 |
| `seed*/seafloor_type.npy` | 500×500 uint8类型，0台地、1浅海、2深海；数组第0行位于图的下方 |
| `seed*/region_types.npy` | 512个地块标签，第0项对应输入分区编号1 |
| `seed*/seafloor.png` | 500×500原尺寸图，PNG第0行位于上方，灰色`#9B9B9B`、浅蓝`#70BCE2`、深蓝`#0D2B63` |
| `seed*/stages.png` | 沿岸目标、完整地块分配、最终类型图三个可见阶段 |
| `seed*/coast_assignment.npz` | 外轮廓坐标km、轮廓编号、海侧地块编号、目标与实际标签 |
| `seed*/targets.json`、`*_segments.json`、`metrics.json` | 随机目标、32个位置候选、实际分段、误差和内部空缺分配 |
| `audit.json`、`tests.json`、`reproducibility.json`、`manifest.json` | 回读检查、测试、固定种子复现、代码与输入输出哈希 |

外轮廓长度按1 km格边计量，真实参考沿用原F的约1 km站点及250 m简化轮廓口径；这两种几何表示的长度差异尚未另行校准。

实现接口依据：[SciPy milp](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html)、[Beta分布](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.beta.html)、[对数正态分布](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.lognorm.html)。这些文档支持计算方法和API用法。自然参考来源及适用限制由本项目的原F数据记录和本轮重算结果提供。
