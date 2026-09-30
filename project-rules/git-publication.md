# Git 与发布规则

## 适用范围

- 仓库：`F:\LEM\.git`。项目只使用这一个本地 Git 仓库，不创建第二个仓库或 linked worktree。
- 分支约定：`private` 保存完整的本地工作历史，包含公开文件以及历史记录、研究材料等本地材料，无 upstream，禁止推送到公开远端。`public` 保存代码、必要的项目计划、当前进展与项目规则，具体路径见本文件“公开范围”。
- 远端及用途：`origin`，远端实际分支名为 `main`；`public` 映射到 `origin/main`。本地配置固定使用 `remote.origin.push = refs/heads/public:refs/heads/main`。

## 规则

### 本地版本保护

项目中的全部文件由 Git 在 `private` 分支跟踪和保存，生成文件和外部依赖除外。排除的文件由 `.gitignore` 列出；push 范围由下文“公开范围”和“发布限制”决定。

术语采用构建工具 Bazel 文档的文件分类。生成文件（generated files，也称派生文件、输出文件）指运行程序得到的文件，项目中已有的“生成产物”指这一类。外部依赖（external dependencies）指从本项目以外获取、供程序使用的文件。模型权重按来源归类：本项目训练或拟合得到的属于生成文件，下载的第三方权重属于外部依赖。

排除内容：

1. 模型权重与拟合参数包。
2. `datasets/` 中的训练数据。
3. 音频与视频，包括无法原样重新生成的合成语音。
4. 程序生成的图像、数组、栅格和压缩包，例如渲染图、抽帧、检查图、界面测试截图和修改前的备份压缩包。
5. 生成模块的运行输出目录（例如 `output/`）。
6. 运行日志：程序运行时写出的日志文件，例如 `.log`、错误输出与 `job-logs/`，包括 `bench/results` 中的运行日志。
7. 外部依赖：供程序读取的外部数据（例如 `references/data`）、下载的第三方模型权重、虚拟环境与安装的依赖包。
8. 缓存与本地文件：Python 缓存、构建和测试缓存，IDE、操作系统和本地环境文件。

继续跟踪的内容包括：

- 代码与配置；说明文档；最终策略、current、AGENTS 与项目规则。
- `docs/` 中的会话归档（含其中保存的用户图片和文档）、工作记录及其中的文字报告和结果表、工作日志、阅读记录、下载记录与发布记录。
- `references/` 中的资料说明、来源与核验记录，论文与参考代码原件（`references/paper`、`references/code`），以及各资料包目录的原有内容，包括资料包自带的日志和图像。
- 生成模块 `sources/` 中的论文、网页、记录、原型与代码副本；其中供程序读取的数据文件按第 7 项排除。
- benchmark 的脚本与 JSON 结果。
- 用户提供的截图与附件。
- 记录外部依赖与生成文件来源的清单，例如下载地址与 SHA-256。

公开范围内的文件同时进入 `public`，两个分支分别保留各自的提交历史。

2026-09-30，yzz 澄清本规则。原话：“我的想法是所有的文件都要被git跟踪、保存，但是模型权重、生成的东西可以不进git”；“日志也排除”；“音频、视频可以和模型权重理解为相同的东西，所以排除”；对名称“生成文件和外部依赖”回复“可以”。`bench/results` 中的运行日志是否排除，yzz 回复“呃，我不知道，我感觉无所谓，你帮我选一个吧”，Agent 按最后一次表态“日志也排除”选择排除。论文与参考代码原件的处理方案，yzz 回复“支持”。来源：本会话源 JSONL `0c6e6646-cd3c-489a-903d-947040ead3fb`（2026-09-30 07:39:02Z 至 09:20:59Z）；改动清单见 `docs/work/2026-09-30-git-rule-clarification/`。

### 公开范围

项目代码、`final-strategy/`、`current/`、`AGENTS.md`、`CLAUDE.md`、`project-rules/` 与策略迁移入口 `final-strategy.md` 同时进入 `private` 和 `public`。`docs/`、`references/` 与 `explainer/` 保留在 `private`；生成文件和外部依赖按“本地版本保护”排除。完整公开路径清单见下文和 `project-rules/public-paths.txt`。公开文件中的本地来源引用不改变被引用材料的公开状态。

生成模块 `sources/` 中的资料不公开，按“本地版本保护”在 `private` 跟踪。公开路径清单以目录列入时，用以 `!` 开头的排除条目排除这类子目录；排除条目优先于其他条目，`*` 匹配任意字符。当前排除条目为 `!data_generation/stage/*/sources/`，覆盖各生成模块及其子管线的 `sources/`。

2026-09-09，yZz 要求修改 public/private 分配并推送，将必备的项目计划纳入公开范围，明确列出 `final-strategy/`、`current.md`、`AGENTS.md`、`CLAUDE.md`。这些文件直接引用的 `project-rules/` 与策略迁移入口 `final-strategy.md` 一并公开，使公开副本具备完整的项目规则和入口。

2026-09-12，yZz要求先更新current与项目文档，再将四个输入阶段分别提交并推至远端。此次明确公开的新增代码目录为 `pipline/mask_generator/`、`pipline/seafloor_generator/`、`pipline/initial_bathymetry/`、`pipline/sea_level/`，四阶段各保留一个公开提交。该范围包含对应代码、配置、测试、许可与说明；生成产物、数据集、环境，以及私有历史与参考文件继续按下述边界处理。指示来源见 `docs/work/2026-09-12-input-stages-closeout/decisions.md` 的U13、U14。

2026-09-17，yZz确认汇聚带抬升工作完成，明确要求更新current与项目文档、按项目规则提交并推送至现有Main。该指示覆盖 `pipline/convergent_uplift/` 的源码、源内设计配置、测试与说明，以及本轮台账、策略和发布范围更新。模块原始资料、拟合参数包、数组、图像、检查产物与运行清单按生成产物规则排除；背景场、其他活动及无关工作不纳入本次新增公开范围。来源见 `docs/work/2026-09-17-convergent-uplift-closeout/decisions.md` U1。远端实际分支名为main，沿用public到origin/main的映射。

2026-09-21，yZz要求更新本轮裂谷工作的current和项目文档，按Git规则提交并推送。此次公开范围为裂谷生成、拟合、资料获取及核验源码，配置、专用检查、显示程序和当前使用说明，按下列具体文件与子目录列入清单。研究过程报告、Notebook、会话归档及导出器副本保留private；原件、参数包、数组、图像和运行产物按忽略规则排除。来源见`docs/work/2026-09-21-rifting-publication/decisions.md` U5。

2026-09-28，yZz要求更新本轮沉降工作的current和项目文档，阅读Git规则后提交并推送。此次公开范围为沉降生成、参数拟合、窗口候选与选择、事件查询、显示和核查源码，专用测试及README、METHOD、SOURCES等必要说明，具体文件列于下方清单。WORK_LOG、会话归档、用户附件、归档适配器及发布过程记录保留private；原始资料副本、拟合包、数组、图像和缓存按忽略规则排除。现有无关修改保持。本轮原话与原始行定位见`docs/work/2026-09-28-basin-subsidence-publication/decisions.md`的U9。

2026-09-29，项目系统按 project-system 1.0.1 更新：任务记录由根目录 `current.md` 拆分到 `current/` 目录（索引、各任务文件与 archive），根目录 `current.md` 删除，`current/` 纳入公开范围；`project-rules/` 新增的规则索引、文档维护规则、外部指向规则和 `pre-automation-reading/` 按既有 `project-rules/` 目录规则公开；`.link/` 与 `references/items/` 保留在 `private`。迁移清单及 yzz 的批准原话保存在 `docs/work/2026-09-29-project-system-update/`。

2026-09-30，yzz 确认 `explainer/` 保留在 `private`，原话：“explainer/进private”。`bench/results` 中的运行日志按“本地版本保护”排除，下次发布时从 `public` 当前版本中删除；`current/T-001.md` 中该日志的路径保持原文。来源同“本地版本保护”2026-09-30 条。

2026-09-30，yzz 指出规则遗漏后问：“对，source/是可以被跟踪、提交到private里的，只是不push，我理解的对吗？”Agent 确认并展示上文 `sources/` 排除条目、“本地版本保护”第 5 项与继续跟踪一条的文字，yzz 回复“可以写”。此前各生成模块用 `.gitignore` 排除整个 `sources/`，使其中的资料不被跟踪；本条起这些资料由 Git 在 `private` 跟踪，由排除条目保持不公开。来源：本会话源 JSONL `0c6e6646-cd3c-489a-903d-947040ead3fb`（2026-09-30 10:00:24Z 至 10:07:47Z）；改动清单见 `docs/work/2026-09-30-git-rule-clarification/`。

2026-09-30，yzz 指出背景垂向运动模块位于 `data_generation/` 下，属于项目代码，应当公开，原话：“你理解一下这个东西的位置和性质行不行？这肯定是要public的啊，你在说什么啊？F:\LEM\data_generation里都是”。该模块此前未公开，源于 2026-09-17 汇聚带抬升发布与 2026-09-18 目录迁移时 Agent 划定的范围，记录中没有 yzz 的相应决定。`data_generation/stage/background_uplif/` 及 `tests/data_generation/stage/background_uplif/` 加入公开路径清单；`output/` 仍按忽略规则排除。来源：本会话源 JSONL `0c6e6646-cd3c-489a-903d-947040ead3fb`，2026-09-30T10:47:26Z。

同日，Agent 列出 `data_generation/` 下另外 13 个被跟踪但未公开的文件；这些文件的私有状态同样来自 2026-09-21 与 2026-09-28 发布时 Agent 划定的范围。yzz 问“你觉得呢？这13个？”，Agent 建议公开裂谷的 8 份模块文档与 Notebook 及沉降的 `WORK_LOG.md`，裂谷 `scripts/conversation_archive/` 中的会话归档导出器副本保留 `private`；yzz 回复“1.对，对话记录这种是一定private 2.保存对话，更新readme，提交然后push”。据此上述 10 个文件加入公开路径清单；会话归档、对话记录及其导出工具副本保留 `private`。来源：本会话源 JSONL `0c6e6646-cd3c-489a-903d-947040ead3fb`，2026-09-30T10:53:55Z 至 11:01:41Z。

公开路径清单保存在 `project-rules/public-paths.txt`。文件名表示该文件，末尾带 `/` 的路径表示整个目录，以 `!` 开头的条目为排除条目。当前清单为：

- `.gitattributes`
- `.gitignore`
- `README.md`
- `launch_terrain_viewer.bat`
- `pyproject.toml`
- `AGENTS.md`
- `CLAUDE.md`
- `current/`
- `final-strategy.md`
- `final-strategy/`
- `project-rules/`
- `viewer/`
- `data_generation/README.md`
- `data_generation/pipeline/README.md`
- `training/README.md`
- `tests/__init__.py`
- `tests/README.md`
- `tests/run.py`
- `tests/suites.json`
- `tests/viewer/`
- `tests/benchmarks/`
- `tests/data_generation/__init__.py`
- `tests/data_generation/stage/__init__.py`
- `bench/results/`
- `data_generation/stage/mask_generator/`
- `tests/data_generation/stage/mask_generator/`
- `data_generation/stage/seafloor_generator/`
- `tests/data_generation/stage/seafloor_generator/`
- `data_generation/stage/initial_bathymetry/`
- `tests/data_generation/stage/initial_bathymetry/`
- `data_generation/stage/sea_level/`
- `tests/data_generation/stage/sea_level/`
- `data_generation/stage/background_uplif/`
- `tests/data_generation/stage/background_uplif/`
- `data_generation/stage/convergent_uplift/`
- `tests/data_generation/stage/convergent_uplift/`
- `data_generation/stage/basin_subsidence/.gitignore`
- `data_generation/stage/basin_subsidence/README.md`
- `data_generation/stage/basin_subsidence/METHOD.md`
- `data_generation/stage/basin_subsidence/SOURCES.md`
- `data_generation/stage/basin_subsidence/WORK_LOG.md`
- `data_generation/stage/basin_subsidence/__init__.py`
- `data_generation/stage/basin_subsidence/common.py`
- `data_generation/stage/basin_subsidence/prepare.py`
- `data_generation/stage/basin_subsidence/fit.py`
- `data_generation/stage/basin_subsidence/spatial.py`
- `data_generation/stage/basin_subsidence/temporal.py`
- `data_generation/stage/basin_subsidence/sampling_geometry.py`
- `data_generation/stage/basin_subsidence/window.py`
- `data_generation/stage/basin_subsidence/resampling.py`
- `data_generation/stage/basin_subsidence/sampling_diagnostics.py`
- `data_generation/stage/basin_subsidence/schedule.py`
- `data_generation/stage/basin_subsidence/pipeline.py`
- `data_generation/stage/basin_subsidence/templates.py`
- `data_generation/stage/basin_subsidence/rendering.py`
- `data_generation/stage/basin_subsidence/verify.py`
- `data_generation/stage/basin_subsidence/main.py`
- `data_generation/stage/basin_subsidence/run.ps1`
- `data_generation/stage/basin_subsidence/open_gallery.ps1`
- `tests/data_generation/stage/basin_subsidence/`
- `data_generation/stage/rifting/.gitignore`
- `data_generation/stage/rifting/README.md`
- `data_generation/stage/rifting/IMPLEMENTATION.md`
- `data_generation/stage/rifting/VISUALIZATION_SPEC.md`
- `data_generation/stage/rifting/GAPS.md`
- `data_generation/stage/rifting/IMPLEMENTATION_PLAN.md`
- `data_generation/stage/rifting/METHOD_REVIEW.md`
- `data_generation/stage/rifting/NUMERICAL_CLOSEOUT.md`
- `data_generation/stage/rifting/PARAMETER_EVIDENCE.md`
- `data_generation/stage/rifting/REPORT.md`
- `data_generation/stage/rifting/SCOPE.md`
- `data_generation/stage/rifting/SOURCES.md`
- `data_generation/stage/rifting/notebooks/evidence_review.ipynb`
- `data_generation/stage/rifting/open_gallery.ps1`
- `data_generation/stage/rifting/run_generation.ps1`
- `data_generation/stage/rifting/run.ps1`
- `data_generation/stage/rifting/acquisition-1.json`
- `data_generation/stage/rifting/acquisition-2.json`
- `data_generation/stage/rifting/acquisition-3.json`
- `data_generation/stage/rifting/acquisition-4.json`
- `data_generation/stage/rifting/acquisition-5.json`
- `data_generation/stage/rifting/acquisition-6.json`
- `data_generation/stage/rifting/engine/`
- `data_generation/stage/rifting/reporting/`
- `data_generation/stage/rifting/checks/`
- `data_generation/stage/rifting/scripts/acquire.py`
- `data_generation/stage/rifting/scripts/build_delivery.py`
- `data_generation/stage/rifting/scripts/extract_web_text.py`
- `data_generation/stage/rifting/scripts/method_checks.py`
- `data_generation/stage/rifting/scripts/prepare_local.py`
- `data_generation/stage/rifting/scripts/profile_magnitudes.py`
- `data_generation/stage/rifting/scripts/profile_sources.py`
- `data_generation/stage/rifting/scripts/quality_checks.py`
- `data_generation/stage/rifting/scripts/verify_delivery.py`
- `data_generation/stage/rifting/scripts/workspace.py`
- `experiments/lem_pipeline/`
- `tests/experiments/lem_pipeline/`
- `experiments/landlab_experiments/`
- `experiments/fastscape_examples/`
- `experiments/README.md`
- `tests/experiments/__init__.py`
- `datasets/README.md`
- `!data_generation/stage/*/sources/`

2026-09-18，按本轮已获执行授权的目录迁移方案，将原公开代码及对应测试映射到上述新位置，并纳入配套的目录说明与集中测试入口。原始历史路径在前文事件记录中保留。本地背景垂向运动源码及其测试继续排除，冻结资源、模型包和生成产物延续既有边界。本轮没有执行 Git 提交或远端发布。迁移依据与核查记录见 `docs/work/2026-09-18-directory-migration/`。

`docs/`（包括历史会话、旧计划、研究过程与运行记录）和 `references/` 保留在 `private`。`datasets/` 的训练数据内容、`output/`、环境与缓存按 `.gitignore` 排除；`datasets/README.md` 作为用途说明公开。参考资料分类修正后，获取原件归入 `references/data`、`references/paper`、`references/code`；2026-09-30 起 `references/paper` 与 `references/code` 中的原件由 Git 在 `private` 跟踪，`references/data` 按忽略规则排除。来源目录与索引继续保留在 private。公开文件中对本地材料的路径引用只保留来源定位，不使被引用的文件进入公开范围；这些引用在公开副本中可能无法访问。用户原话与来源定位保持原文。

2026-09-18，按用户随后明确的分类纠正，将三组旧流程与实验移至 `experiments`，相应测试移至 `tests/experiments`。`datasets` 专用于训练数据；外部参考原件归入 `references` 的分类目录。本次修正没有执行提交或推送。

新增公开文件、公开文案或扩大范围需要 yZz 明确批准。

#### 既有公开贡献历史

为保留31415在体素查看器中的真实提交作者记录，允许将 `origin/litho-3d-and-map-viewer` 的下列两个既有公开提交历史并入public：

- `4888087d32b56eba2d3490090d50567ba83fd668`
- `748f24f63820309ae89e319a0722372a325fc8f3`

该项使用以现有public和上述公开分支为父提交的合并记录，当前程序源码保持。通过普通快进推送更新origin/main，不修改既有提交作者、时间或已发布提交，不引入private独有历史。

这两条完整提交号保存在 `project-rules/public-history-commits.txt`。pre-push仍逐条检查待发布提交的完整文件树；仅这两条不可变历史提交按其自身保存的公开路径清单核验，其他提交继续按待推送public版本的当前清单核验。该例外不允许在当前文件树恢复旧目录，也不得自动追加其他历史提交。

### 提交与署名

沿用本项目已经确定的提交身份，遵守 AGENTS 中的 Agent 署名限制。具体身份与记录要求：提交沿用仓库现有的 yZz 身份。不得添加 Agent 共同作者、Agent 提交作者或 Contributors 署名。

## 操作与记录

### 发布限制

1. 只允许 `refs/heads/public` 推送到 `refs/heads/main`。
2. 禁止推送 `private`、其他分支、tag 或全部 refs。
3. 禁止使用 `git push --all`、`git push --mirror` 和绕过 pre-push 检查的参数。
4. 推送前检查待发送提交的文件树和提交历史。
5. 检查待发送的每个提交的完整文件树；出现公开清单之外或排除条目下的文件时停止推送并报告。公开文件内的本地路径引用按本文件“公开范围”处理。
6. 禁止合并、推送或以其他方式使 `private` 独有的提交历史进入公开远端。公开提交以已有 `public` 提交为父提交，从已提交的 `private` 快照中选取公开文件。

版本化检查脚本为 `project-rules/pre-push`，安装到本地 `.git/hooks/pre-push` 后检查远端名、ref 映射、快进关系和待发送历史的文件树。检查使用待推送提交中的 `project-rules/public-paths.txt`，包括其中的排除条目。`.gitattributes` 固定这两个文件使用 LF 换行。不得通过关闭或绕过 hook 发布。

### 单工作目录发布流程

1. 核对现有修改与后台写入。在 `private` 提交本次工作快照，记录用于发布的提交号。保留与本次发布无关的修改；后台后来产生的文件留到下一次提交。
2. 按 yZz 当前指令确定本次公开范围和文本。用户已明确要求公开并推送指定文件时，使用其当前内容；不重复请求同一范围的批准。新增范围须更新本文件“公开范围”和公开路径清单。
3. 核对 `origin/main` 与本地 `public`。正常发布只作快进推送。
4. 首选在同一 `.git` 中使用临时 `GIT_INDEX_FILE`：由已提交的 `private` 快照读取文件树，只保留公开路径并去掉排除条目下的文件，检查差异后用 `git write-tree` 与 `git commit-tree` 创建以当前 `public` 为唯一父提交的公开提交。用带旧提交号校验的 `git update-ref` 更新 `public`。当前工作目录、当前分支与常规索引保持在 `private`；不创建第二个仓库或 linked worktree。
5. 对照公开清单和来源快照，核对公开提交的路径、文件内容、父提交与待发送历史。同步安装并测试 pre-push 检查。
6. 执行普通 `git push origin`。本地 refspec 和 pre-push 检查只允许 `public` 到 `origin/main`。
7. 用远端查询确认 `origin/main` 等于本地 `public`，并复核当前分支和工作树状态。

没有后台任务且工作树为空时，也可以在同一工作目录切换到 `public`，只取回公开清单中的路径并提交，推送后切回 `private`。`private` 独有文件会在切换期间暂时移除，因此使用前必须确认没有任务依赖这些文件。

提交或发布前核对：待发送提交的完整文件树不含公开路径清单之外或排除条目下的文件；公开提交以当前 `public` 为唯一父提交，不引入 `private` 独有历史；pre-push 检查已安装且未被绕过；推送后用远端查询确认 `origin/main` 等于本地 `public`。

本文件记录实际存在或已经确定的机制；未确定的远端、分支或公开范围如实注明。
