# 实验与旧流程

本目录保存可运行的旧流程、早期生成实验及示例复现程序。它们与当前数据生成阶段分别组织。

| 目录 | 用途 |
|---|---|
| lem_pipeline | 旧版完整生成流程及其配套校准、统计和批次入口；Python 包名继续为 lem_pipeline |
| landlab_experiments | 早期 Landlab 地形生成与参数实验 |
| fastscape_examples | Fastscape 演化实验、官方示例复现及其共同驱动 |

相关测试和数值验证位于 [tests/experiments](../tests/experiments)。统一测试入口及环境选择见 [测试说明](../tests/README.md)。

这些程序保留其原有方法和结果身份。后续正式采用的实现需要经过集成与验证，纳入完整的数据生成管线。
