# 水下台地二维区域掩膜

2026-09-12，yZz确认数据4与数据1已完成，数据4的初始台地形状成果纳入本轮验收。原话与收尾范围见 [用户确认](../../../docs/work/2026-09-12-input-stages-closeout/decisions.md#u13)。具体工程方法与资料限制继续保留，后续LEM联调和终态验证按对应阶段推进。

当前采用 **World Orogen平面分区与整组选区Gibbs抽样，512分区、外围3层完整分区禁选**。输出为500×500布尔掩膜，格距1 km，标记初始水下台地范围。当前入口为：

```powershell
& F:\LEM\data_generation\stage\mask_generator\run_world_orogen_gibbs.ps1
```

默认只运行这一种配置，新产物写入 `F:\LEM\output\mask_generator\world_orogen_gibbs_512_layers_3`。其余数值沿用已选批次；中心可取消，50%至60%仅为面积偏好，分离部分与内部空缺保留。

- [选定配置与用户原话](world_orogen_gibbs/SELECTED_PROFILE.md)
- [当前实现、输入输出和运行说明](world_orogen_gibbs/README.md)
- [项目策略中的形状规则](../../../final-strategy/architecture-dataflow.md#platform-mask)

| 入口 | 用途 |
| --- | --- |
| `run_world_orogen_gibbs.ps1` | 当前采用的512分区、3层禁选形状生成器 |
| `run_world_orogen.ps1` | 先前单向增加分区的World Orogen对照 |
| `run.ps1`、`run.py` | 椭圆包络和参考形状叠加的历史A/B对照 |

海域分配、初始海底和海平面已由相邻三个模块提供，数据1已纳入本轮验收；地质活动、过程参数与Fastscape统一接入继续按后续任务推进。以下内容保留A/B程序的复现口径，默认参数与输出数量均指该历史程序。

## 历史A/B对照的运行

在 PowerShell 中执行：

```powershell
& F:\LEM\data_generation\stage\mask_generator\run.ps1
```

默认输出 `F:\LEM\output\mask_generator`，依次执行代码测试、参考数据准备、方法 A 校准、六组配对生成、导出和交付核查。默认使用现有 D 会话隔离环境：

```text
F:\LEM\docs\work\2026-09-08-q1-data\D-landform-statistics\.venv\Scripts\python.exe
```

脚本不安装依赖，也不写入 `lem-env`。依赖为 NumPy、SciPy、Shapely、pyproj、Matplotlib 和 Pillow；实际版本与 Python 路径保存在产物的 `manifest.json`。测试使用标准库 unittest。

默认进程预算为 8，包含协调进程。校准最多创建 7 个子进程，每个子进程以及协调进程均固定使用一个 CPU，数值库线程数为 1。参考准备、最终导出和核查在协调进程中执行。CPU 设置仅作用于本次进程树。

可按阶段执行：

```powershell
& F:\LEM\data_generation\stage\mask_generator\run.ps1 -Stage test
& F:\LEM\data_generation\stage\mask_generator\run.ps1 -Stage prepare
& F:\LEM\data_generation\stage\mask_generator\run.ps1 -Stage calibrate -Workers 8
& F:\LEM\data_generation\stage\mask_generator\run.ps1 -Stage generate
& F:\LEM\data_generation\stage\mask_generator\run.ps1 -Stage audit
& F:\LEM\data_generation\stage\mask_generator\run.ps1 -Stage report
```

`generate` 读取已准备的参考数据和校准配置，生成全部六组结果并核查。`audit` 重新运行六组随机函数作复现核对，不改掩膜；`report` 仅重建查看页、总览及清单。默认种子固定。参考输入哈希和校准对应的参考版本不一致时停止，需重做相关前置阶段。

重复执行会覆盖本生成器同名产物。已有输出目录必须含本程序的身份标记 `.mask_generator.json`；程序拒绝写入其他已有内容的目录。`-Output` 可用于另存一批；`-PythonPath` 可指定具有同等依赖的现有隔离环境。计算代码和启动脚本保存在本目录，测试集中于根目录的 tests/data_generation/stage/mask_generator，运行时不导入旧生成器或其他会话代码。

## 目录与调用接口

```text
mask_generator/
  run.py, run.ps1                 统一执行入口
  ellipse/generator.py           方法 A 随机函数
  ellipse/calibrate.py            方法 A 固定候选搜索
  reference_overlay/generator.py  方法 B 随机函数
  common/                        数据、随机场、统计、轮廓、导出、查看页
```

在本目录作为 Python 导入搜索路径的情况下：

```python
from pathlib import Path
from common.reference import load_reference
from common.io import read_json
from common.numerics import shared_sample
from ellipse.generator import generate_ellipse_mask
from reference_overlay.generator import generate_reference_mask

output = Path(r"F:\LEM\output\mask_generator")
reference = load_reference(output / "reference")
selected = read_json(output / "calibration/selected.json")
shared = shared_sample(1001)  # 可指定 target_fraction=0.55
a = generate_ellipse_mask(1001, reference, selected, shared=shared)
b = generate_reference_mask(1001, reference, shared=shared)
assert a.mask.dtype == bool and a.mask.shape == (500, 500)
```

两个函数返回 `MaskResult`，包含 `mask`、`envelope`、`combined`、共享条件、阈值和方法参数。单独调用时也按同一子序列规则重建随机场，无需事先运行另一种方法。函数不在采样过程中进行校准。

## 输入身份和口径

| 输入 | 位置与用途 |
| --- | --- |
| 34 个成员 | `docs/work/2026-09-08-q1-data/merged/data-package/pop34/population-members.csv`，成员顺序、ID、名称和投影中心 |
| 原始岸线 ID | `docs/work/2026-09-08-q1-data/D-landform-statistics/tables/reference-landmasses.csv`，连接成员 ID 与 GSHHG ID |
| 原始矢量 | `references/data/2026-09-08-q1-data/D/gshhs_f.b`，GSHHG 2.3.7 full-resolution level-1 外海岸 |
| 原尺度参考栅格 | `references/data/2026-09-08-q1-data/D/derived-1km-masks/<id>.npz` 中的 `focal`，用于方法 A 的参考统计 |

所有输入均只读，逐文件保存 SHA-256。`focal` 是目标陆块的外海岸范围，沿用 D 会话包含封闭湖泊的形状统计口径；`land` 可能包含邻近陆地，未用于校准。方法 B 从原始矢量外海岸读取形状，封闭湖泊按相同口径处理，与外海连通的凹湾保留。

历史背景可追溯到 `docs/sessions/2026-09-07-lem-continent-generation-methods-67775e98/conversation.md` 和 `docs/sessions/2026-09-09-lem-pipeline-execution-marine-recovery-639e9e4e/conversation.md`。历史记录提供来源与时间顺序。本轮明确批准的生成规则用于此次实现，旧谱指数文件未作为参数输入。

## 公共生成流程

1. 通过 NumPy PCG64 和 `SeedSequence([seed, role_id])` 划分随机数子序列。占比角色 11，位置和方向角色 12，A 的参考残差抽样角色 13，随机场角色分别为 101、105、125。
2. 未给定占比时均匀抽取 0.50 至 0.60；方位角均匀抽取 0 至 360°；中心坐标由 (250,250) km 两轴各均匀加上 −25 至 25 km。每个种子的两种方法共享这些数值。
3. 三个角色分别生成 524×524 独立标准正态随机数。方形局部平均窗口为 1×1、5×5、25×25；截取中央 500×500，所有有效窗口均有足够外围数据。各场在中央块内减均值、除总体标准差。
4. 各方法生成包络，将本次 500×500 数值块线性归一化为 0 至 1。以独立场的固定基础系数 0.005、0.015、0.050 叠加。A 再乘候选强度倍率，B 倍率恒为 1。
5. 允许区域为行列索引 10 至 489，共 480×480 格。仅在允许区域中求第 N 大数值，N 为 Python `round(target_fraction*250000)`，四舍六入，恰好半格采用偶数舍入。同值按从小到大的行优先扁平索引补足。
6. 保留全部选中格子，完全不做填洞、删除小块或平滑。目标格数由阈值精确控制。

局部平均窗口、基础系数、中心变化范围和边带属于工程设定。方形窗口具有方向性，其空间联系属于该定义的结果。三个窗口的独立底层数据和局部平均计算分别测试；标准化后的相邻水平格相关系数期望近似为 0、0.8、0.96。

## 方法 A：椭圆包络与校准

原始包络为 `1-sqrt((x/a)^2+(y/b)^2)`，x、y 为相对于随机中心、旋转到随机长轴方向的局部公里坐标。按目标面积与轴比计算半轴 `b=sqrt(area/(pi*ratio))`、`a=b*ratio`。归一化后，最终面积由阈值确定。

参考统计对 34 个陆块等权，分别拟合 `log(metric)=intercept+slope*log(area_km2)+residual`，保留全部 34 个残差。长宽比来自面积协方差特征值之比的平方根；栅格采用格中心并加入单格均匀面积协方差 `1/12 km²`。岸线使用四方向 Crofton 估计，岸线发育系数为 `P_crofton/(2*sqrt(pi*coastal_envelope_area))`。

长宽比参数从目标面积下的预测加等权抽取的参考残差得到，低于 1 时取 1。伸长倍率作用于其对数，具体为 `ratio=max(1,raw_ratio)**stretch`。这一定义、轴比下限、残差来源成员和面积是否超出参考范围均记录在样本参数中。

| 项目 | 固定值 |
| --- | --- |
| 伸长倍率 | 0.50、0.75、1.00、1.25、1.50 |
| 共同强度倍率 | 0.50、1.00、2.00、4.00 |
| 校准种子 | 0 至 63，所有候选使用相同 64 个 |
| 总样本数 | 20×64=1280，只保存配置与统计 |
| 两项比较指标 | 主轴长宽比、Crofton 岸线发育系数 |
| 距离 | 生成值与参考值的对数面积残差分布之间的 Wasserstein-1 距离 |
| 归一化 | 各项除以 `max(参考残差IQR,0.1)` |
| 总损失 | 两项等权相加 |

使用面积残差比较，将每份不同目标面积的生成值校正到统一的参考关系；等价于在相同目标面积平移对应的参考对数分布。误差完全相同时，按伸长倍率、强度倍率升序确定配置。保存所有 1280 行样本统计、20 行候选误差、完整校准记录及选定参数。

分块、最大块比例、填充比例、内海几何代理和边界接触只作诊断，均未计入校准损失。

## 方法 B：参考形状等权叠加

每个陆块从原始矢量投影到其局部 Lambert 方位等面积坐标，单位 km。先按多边形面积中心平移，再按连续多边形面积协方差长轴旋转。长轴正向使该方向的三阶中心面积矩为正；三阶矩接近零时使用局部 x 分量为正、再按 y 为正的固定规则，近各向同性时选择局部 x 轴。方向规则只定义叠加的几何对齐，不赋予地学上的共同东西方向。

最长跨度定义为凸包任意两点之间的最大欧氏距离。每个矢量等比例缩放，使此距离等于相对长度 1，保留长宽关系；不拉伸任一单轴，也不按最终目标面积缩放单个参考陆块。

相对长度 1 对应 500 个像素，共同画布为 1024×1024，原点在画布中心。先完成原始矢量的连续变换，再按像素中心栅格化。34 张布尔数组以 1/34 等权相加。保存整数覆盖次数以及 float64 平均值，核查逐项重加能还原包络。

生成时以共同位置和方向反变换最终 500×500 的格中心，再对 1024×1024 叠加场双线性取样，形成对应数值块。一个输出格对应一个中间像素；输出格最终被赋予项目 1 km 格距。双线性插值仅用于连续包络的坐标取样，最终布尔掩膜和 PNG 均未插值。原始包络的非零范围不承担最终 50% 至 60% 面积约束，面积在阈值阶段控制。

方法 B 固定使用 34 个成员、相同权重及基础系数。代码未调用方法 A、拟合或校准入口。最终统计和图片只供对照，不反向调节 B。

## 输出与坐标

```text
output/mask_generator/
  reference/                    成员、输入哈希、对齐记录、34 张形状、叠加场
  calibration/                  1280 行统计、20 个配置、选定值、图表
  seed1001/{ellipse,reference_overlay}/
  ...
  seed1006/{ellipse,reference_overlay}/
  comparison.png                六行两列，保留每张原图的 500×500 像素
  report.html                   本地配对查看页
  summary.csv                   十二份结果的关键指标
  audit.json                    文件数量、配对、图像和轮廓还原、复现核查
  unit_tests.json, unit_tests.log
  visual_review.json            实际图像检查记录，生成过程不自动声称外观通过
  manifest.json, run_status.json
```

每份样本保存 `mask.npy`（bool）、`envelope.npy`、`noise_1.npy`、`noise_5.npy`、`noise_25.npy`、`combined.npy`（均 float64），各自的 PNG，以及 `contours.json`、`contours.png`、`config.json`、`metrics.json`、`status.json`。

数组行号随 y 增大，`mask[row,column]` 的格中心为 `(column+0.5,row+0.5)` km，原点为域左下角。PNG 以地图方向显示，顶行对应 NPY 最后一行。`decode_mask_png` 按固定两色解码并反转行序，可逐格还原 bool 数组。台地 RGB=(220,230,211)，其他区域 RGB=(22,41,64)。图片原尺寸 500×500，无文字、插值或平滑。

轮廓为占据格子的精确边缘，多边形通过逐行连续格子矩形的并集取得，完整保存外轮廓和内轮廓。每个坐标采用局部公里单位；外轮廓逆时针，内轮廓顺时针，环首尾闭合。面积与 bool 格数精确相等，轮廓重新栅格化须逐格还原输入。点接触在矢量拓扑和离散 4/8 邻接下的环计数可能不同，二者均记录，掩膜不被修改。

连续场 PNG 的色标固定：包络 0 至 1；各随机场 −3 至 3；组合场 −0.25 至 1.25。色标外的颜色截断只影响预览，NPY 始终保留完整值。

## 检查与解释范围

代码测试、几何核查、统计对照和自然外观检查分别保存。自动检查包含：34 个成员齐全、相同权重、对齐一致性、窗口局部相关、独立子序列、精确阈值、面积和边带、轮廓重栅格化、图像解码、两种方法共用基础场、B 固定参数以及最终结果复现。

岸线统计在测量副本中包含封闭水体，保持参考外海岸口径；原掩膜中的空缺完整保留。连通块按台地 4 邻接、水体 8 邻接计算，并另记台地 8 邻接数。最大连通块的形状另列，主指标始终针对全部台地。

填充比例使用按 3°间隔搜索的最小外包正方形近似值，仅用于诊断。内海几何代理采用半径 5、10、20、40 km 的闭运算，统计与原外海相连、闭运算后残留且失去外界连接的至少 100 km² 水域，其地学含义尚未验证。

外圈 10 格在阈值前排除，可使台地在允许区域边缘产生连续直线接触。逐边保存接触总格数与最长连续长度，并记录被排除区域中高于最终阈值的格数。连续接触达到 25 km 时自动标记，25 km 属于本次图像检查的工程提示阈值，未用于删除样本或调整参数。另存等面积圆和正方形的交并比作为外观诊断，未将其作为自动验收条件。

查看顺序为 `reference/aligned_shapes.png`、`reference/coverage.png`、`comparison.png` 和 `report.html`。需要修改设计时，应保留本批次数值与检查记录并明确新条件，再执行下一批实验。

## 本次运行记录

2026-09-10 的固定搜索选出 A 的伸长倍率 1.00、共同强度倍率 0.50，损失约 1.046908。B 的参数保持固定。六个种子的实际占比分别为 50.5944%、59.6568%、52.4852%、50.8680%、57.6324%、50.4672%，每组 A、B 完全一致。

已导出并查看总览。A 的 1001 和 1003 存在明显边带长直边，最长连续接触分别为 263 km 和 197 km；A 的 1002 和 1004 整体接近圆形。B 的六份结果各有 677 至 862 个四连通块，外围出现较多分离部分和方向明显的细部。上述结果按既定算法保留，具体观察与用户验收状态见输出目录的 `visual_review.json`。

浏览器工具的本地文件 URL 策略阻止了对 `report.html` 的实际浏览器访问。查看页已生成，JSON 序列化回归测试通过；浏览器交互检查尚未完成。可由用户在本地浏览器中打开该文件检查视图切换。
