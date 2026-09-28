# 来源与模板复用

## 地质资料

| 来源 | 内容及用途 | 本地入口 |
|---|---|---|
| Han、Sun、Wang、Zhao，2021；Han等，2023，B07 | 曾母与北康盆地回剥卸载构造沉降量及速率；用于空间强度与配对时间曲线 | [数据集](https://doi.org/10.6084/m9.figshare.14345750.v1)，[论文](https://doi.org/10.1007/s00343-022-1430-9) |
| Dvorak等，2023/2024，B01 | 坎特伯雷回剥历史与热沉降阶段；用于寿命约束，异常相邻差分保持诊断身份 | [论文](https://doi.org/10.1080/00288306.2023.2214368) |
| Lee和Wagreich，2016/2017，B03 | 维也纳盆地分阶段构造沉降、区域结构与完整尺度 | [论文](https://doi.org/10.1007/s00531-016-1329-9) |
| Hölzel等，2008，B05 | 维也纳区域回剥与空间图；与B03按同一地区研究家族处理 | [论文](https://ajes.at/images/AJES/archive/Band%20101/hoelzel_et_al_ajes_v101.pdf) |

B07数据许可为CC BY 4.0。来源作者、原始文件名称、元数据、字节数和SHA-256保存于[sources/manifest.json](sources/manifest.json)。本模块读取回剥卸载结果，正演结果没有混为观测样本。原始空间位置保持配对；同一剖面的1,818个位置不计作1,818个天然活动。

原资料身份、已取得与未取得的内容继续见[盆地资料记录](../../../references/2026-09-13-geological-activity-parameters/records/basin.md)。B03完整长度与研究域尺度分别保存。原图的插值、外推或无约束区域没有被填成零值测量。

## 本地代码复用

| 既有内容 | 本轮使用 |
|---|---|
| `convergent_uplift/time_pipeline/timing.py` | 适配累计风险调度、自然寿命保留、跨世暂停、阶段取帧；使用新的沉降参数 |
| `convergent_uplift/window_pipeline/render_windows.py` | 冻结并直接加载`bar_size`、`draw_base`和`base_lines`，复用图幅与导出布局 |
| `convergent_uplift/time_pipeline/render_time.py` | 冻结并直接加载`draw_axes`和`stage_label`；阶段文字适配为增强、维持、减弱 |
| `viewer/lem_viewer/colormaps.py` | 冻结并直接复用FEM十二级色表 |
| `convergent_uplift/window_pipeline/bases/seed1001`至`seed1008` | 只读复用已有台地及初始海底；生成前后核对原文件哈希 |
| `mask_generator/world_orogen_gibbs/model.py` | 借鉴整组概率、可选可取消状态与空间偏好；新模型定义连续速率、明确的目标分布及节点更新 |

模板冻结副本位于本模块`sources`。通过AST只加载上述指定函数，隔离原模块的路径和写入入口。原模块代码与产物保持。

## 设计来源

2026-09-27的对话确认直接生成完整成熟期二维参考场，随后生成时间变化；确认零值与非零速率共同生成；确认复用汇聚A至E展示，A图替换为实际网格与节点速率。对应[归档](../../../docs/sessions/2026-09-28-basin-subsidence-window-sampling-16ac7f94/conversation.md)第14、18、20、25条。

2026-09-28的窗口修订采用台地覆盖上限70%、50%起减权、小事件下限豁免，以及所有尺寸共有并随尺寸增强的深部概率衰减。以第44、46条用户纠正和第49、50条范围总结与执行指示为准。具体系数保持实现设计值身份。第59条要求用新版代码生成4组A至E图，固定种子1001、1004、1005、1006的结果独立保存。

本轮数学系数、网格密度及具体数值取舍由实现记录说明，不额外标注为用户逐参数批准。当前工作范围为沉降独立模块与展示；Git提交、远端发布及完整LEM运行保持各自范围。

2026-09-28的文档、提交与推送指示产生于归档之后，确切文本和原始JSONL定位见[本轮U9](../../../docs/work/2026-09-28-basin-subsidence-publication/decisions.md#u9)。该发布不扩展至完整LEM或训练结果。
