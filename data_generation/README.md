# 数据生成

`stage/` 保存当前分阶段开发的数据生成模块。`pipeline/` 预留后续完整集成实现。

| 位置 | 用途 |
|---|---|
| [stage/mask_generator](stage/mask_generator/README.md) | 初始水下台地掩膜 |
| [stage/seafloor_generator](stage/seafloor_generator/README.md) | 海域类型分配 |
| [stage/initial_bathymetry](stage/initial_bathymetry/README.md) | 初始海底高程 |
| [stage/sea_level](stage/sea_level/README.md) | 年代海平面曲线 |
| [stage/background_uplif](stage/background_uplif/README.md) | 背景垂向运动，本地阶段实现 |
| [stage/convergent_uplift](stage/convergent_uplift/README.md) | 汇聚带空间场与独立事件 |
| [stage/rifting](stage/rifting/README.md) | 大、小尺度作用、时变应力、条件断层与构造U的独立首版 |
| [pipeline](pipeline/README.md) | 后续完整集成实现的目录 |

全仓集中测试入口见 [tests](../tests/README.md)。裂谷本轮专用检查位于其`checks/`目录，由`run_generation.ps1 -Stage tests`执行。阶段入口继续使用已有计算环境，外部参考输入从 [references/data](../references/data/README.md) 读取，裂谷的冻结副本保存在模块本地`sources/`。根目录 [datasets](../datasets/README.md) 专用于训练数据，旧流程与早期实验保存在 [experiments](../experiments/README.md)。阶段产物及冻结副本保持各自来源和结果身份。

2026-09-18，yZz确认全仓代码结构与存储位置修复完成，见 [T-011](../current.md#t-011)。本文件描述已完成整理的目录职责；各阶段方法、完整数据生成管线的实现与联调仍按各自任务和项目策略推进。

2026-09-21，裂谷首版已交付种子1001的检查样本：2000 km辅助域、固定500 km窗口、6个大尺度作用、4个小尺度作用、16条断层和243个同步时刻。小尺度图以零应力白色基准和独立色标显示。1 km查询格距与31.25 km应力、25 km断层响应求解格距分别标注；网格收敛、长期响应及完整LEM联调继续核验。
