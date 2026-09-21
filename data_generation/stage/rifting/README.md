# 裂谷生成与时空检查

状态：已实现三类概率生成、时变应力、条件断层、构造U与完整图集。当前交付为检查样本，数值收敛与长期地学校准尚未完成。

首先阅读 [首版实现与检查结果](IMPLEMENTATION.md)。运行 [open_gallery.ps1](open_gallery.ps1) 后打开 [本地时空图集](http://127.0.0.1:8767/)。查看器支持同步时间、空间缩放、逐格方向与实际读值。

当前样本：辅助域2000×2000 km，数据域500×500 km，6个大尺度作用、4个小尺度作用、16条断层、243个同步时刻。前三类应力各27页详细九宫格，另各附一页0至48 Myr全程总览，逐格原图24,000×24,000像素。使用viewer的FEM十二级色板。1 km是查询格距，当前应力求解格距31.25 km，断层响应求解格距25 km。

26项程序检查通过。保持物理源固定的网格比较仍有明显差异，当前结果尚未作为正式训练数据验收。具体误差、代理数据和设计先验见实现说明。

小尺度应力仅显示该分量，零值留白，非零值使用0至28.4578 MPa范围的FEM十二级，跨时间固定；单帧、逐格原图与九宫格同步。27项原交付检查包含一次性工作树范围核对；后续授权的文档与提交变化单独记录，常规产物复核保留数值、图像和来源一致性检查。

| 文件 | 内容 |
|---|---|
| [IMPLEMENTATION.md](IMPLEMENTATION.md) | 三个模型、实际计算方法、当前结果与数值限制 |
| [输出摘要](output/generation_v1/seed1001/review/sample_summary.json) | 当前样本的精确计数、尺度与范围 |
| [REPORT.md](REPORT.md) | 第一轮资料核验报告，保留原有阶段归属 |
| [PARAMETER_EVIDENCE.md](PARAMETER_EVIDENCE.md) | 力、条件断层、确定性U与适配的逐参数依据 |
| [METHOD_REVIEW.md](METHOD_REVIEW.md) | 方法来源、代码核对、已执行数值算例及适用范围 |
| [GAPS.md](GAPS.md) | 具体缺口、受影响对象及下一步操作 |
| [SOURCES.md](SOURCES.md) | 现有资料、新来源、版本及阅读范围 |
| [SCOPE.md](SCOPE.md) | 当前授权、用户设计与候选实现的归属 |
| [VISUALIZATION_SPEC.md](VISUALIZATION_SPEC.md) | 七类视图、九宫格同步、逐格原图与时间采样方案 |
| [notebooks/evidence_review.ipynb](notebooks/evidence_review.ipynb) | 已执行的关键资料与运动约束核验 |

`sources/`保存原件，`output/tables/`保存派生参考表，`output/checks/`保存第一轮核验，`engine/`保存生成程序，`output/generation_v1/seed1001/`保存当前样本。旧检查样本单独保留，当前图集不读取旧历史。

## 运行

生成阶段使用LEM环境，所有输出留在本目录。`all`依次重建参数、样本、图集与检查，默认`verify`仅复核已有交付。

```powershell
& F:\LEM\data_generation\stage\rifting\run_generation.ps1 -Stage verify
& F:\LEM\data_generation\stage\rifting\run_generation.ps1 -Stage gallery
& F:\LEM\data_generation\stage\rifting\run_generation.ps1 -Stage all -Seed 1001 -Workers 6
```

`all`会覆盖选定种子的当前输出。首版参数为显式代码默认值，重新拟合会重建这些默认值。调参实验应使用独立输出并记录参数身份。

`verify`核对保存数组、图像和来源。需要另行核对最初资料获取阶段的工作树范围时，可在模块目录运行`python -B -m engine.verify --check-workspace-scope`；常规产物复核会记录该快照之后的目录外状态变化。

以下入口保留第一轮资料核验：

使用已存在的两个Python运行时，不安装依赖：LEM环境执行数值算例；Codex随附Python只读分析原始工作簿及PDF。各阶段输出都在本目录。

```powershell
& F:\LEM\data_generation\stage\rifting\run.ps1 -Stage verify
& F:\LEM\data_generation\stage\rifting\run.ps1 -Stage profile
& F:\LEM\data_generation\stage\rifting\run.ps1 -Stage checks
& F:\LEM\data_generation\stage\rifting\run.ps1 -Stage report
```

`verify` 核查冻结资料、报告链接、来源哈希和目录外状态；不重新拟合或运行LEM。`profile` 重新读取数据并提取工作簿/PDF；`checks` 执行本轮专门数值算例和质量核查；`report` 从保存结果重建报告与Notebook。

新机器首先运行 `scripts/prepare_local.py` 冻结所列项目已有资料，再按顺序将 `acquisition-1.json` 至 `acquisition-6.json` 传给 `scripts/acquire.py` 获取公开原件。这些地址和版本固定；失败状态保留。离线复核可以直接使用现有冻结副本。

第一轮报告描述当时的资料核验状态。当前新增的生成实现、修正与结果以IMPLEMENTATION.md及当前输出清单为准；这些内容不改变用户验收状态。

## 版本保护与发布

公开内容为生成、拟合、获取与核验代码，配置，专用检查，显示程序和当前使用说明。研究过程报告、Notebook、会话归档及归档导出器副本保留在private；原始副本、参数包、数组、图像与运行产物按`.gitignore`排除。公开说明中的本地证据链接可能无法在公开副本中访问。新环境需要先准备说明中列出的参考资料与冻结输入。

本次规范会话归档位于[项目已有会话目录](../../../docs/sessions/2026-09-21-rift-forcing-model-discussion-5879be47/conversation.md)。早先放在模块内的副本保留在本地并排除版本跟踪。
