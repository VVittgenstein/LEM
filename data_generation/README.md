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
| [stage/rifting](stage/rifting/README.md) | 大、小尺度作用、时变应力、条件断层与构造U，独立阶段已收口 |
| [pipeline](pipeline/README.md) | 后续完整集成实现的目录 |

全仓集中测试入口见 [tests](../tests/README.md)。裂谷本轮专用检查位于其`checks/`目录，由`run_generation.ps1 -Stage tests`执行。阶段入口继续使用已有计算环境，外部参考输入从 [references/data](../references/data/README.md) 读取，裂谷的冻结副本保存在模块本地`sources/`。根目录 [datasets](../datasets/README.md) 专用于训练数据，旧流程与早期实验保存在 [experiments](../experiments/README.md)。阶段产物及冻结副本保持各自来源和结果身份。

2026-09-18，yZz确认全仓代码结构与存储位置修复完成，见 [T-011](../current.md#t-011)。本文件描述已完成整理的目录职责；各阶段方法、完整数据生成管线的实现与联调仍按各自任务和项目策略推进。

2026-09-21，裂谷独立阶段在原首版交付之后完成数值比较与性能取舍，已按用户要求收口。当前配置为应力97×97×5、断层升降65×65×9节点，输出查询格距1 km；11组网格比较和8份并行输入生成通过，数值配置保留设计取值身份。原16条断层、243个时刻的图集保持原样，新配置产物独立保存。范围与数据见[数值收口报告](stage/rifting/NUMERICAL_CLOSEOUT.md)；完整LEM联调继续属于完整管线工作。

本次数值工作为网格参数选择与性能验证，既定生成逻辑保持，配置名称用于复现参数。选窗与断层生成的理论关系及当前实现顺序分别见[裂谷架构说明](../final-strategy/architecture-dataflow.md#rifting-spacetime)；讨论原文见[本次归档](../docs/sessions/2026-09-21-rifting-numerical-closeout-55c795ef/conversation.md)。
