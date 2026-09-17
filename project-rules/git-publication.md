# Git 本地保护与公开发布规则

## 1. 仓库结构

项目只使用 `F:\LEM\.git` 一个本地 Git 仓库，不创建第二个仓库或 linked worktree。

| 分支 | 内容 | 远端关系 |
|---|---|---|
| `private` | 保存完整的本地工作历史，包含公开文件以及历史记录、研究材料等本地材料。 | 无 upstream，禁止推送到公开远端。 |
| `public` | 保存代码、必要的项目计划、当前进展与项目规则，具体路径见第 3 节。 | 映射到 `origin/main`。 |

本地配置固定使用：

```text
remote.origin.push = refs/heads/public:refs/heads/main
```

## 2. `.gitignore`

`.gitignore` 只用于排除无需版本保护的未跟踪文件。它不决定 push 范围。

排除内容包括：

- `output/` 中的二进制产物。
- 虚拟环境。
- Python 缓存、构建产物和测试缓存。
- IDE、操作系统和本地环境文件。

最终策略、current、Agent 规则、`docs/` 和 `references/` 继续在 `private` 分支中被跟踪。公开范围内的文件同时进入 `public`，两个分支分别保留各自的提交历史。

## 3. 公开范围

2026-09-09，yZz 要求修改 public/private 分配并推送，将必备的项目计划纳入公开范围，明确列出 `final-strategy/`、`current.md`、`AGENTS.md`、`CLAUDE.md`。这些文件直接引用的 `project-rules/` 与策略迁移入口 `final-strategy.md` 一并公开，使公开副本具备完整的项目规则和入口。

2026-09-12，yZz要求先更新current与项目文档，再将四个输入阶段分别提交并推至远端。此次明确公开的新增代码目录为 `pipline/mask_generator/`、`pipline/seafloor_generator/`、`pipline/initial_bathymetry/`、`pipline/sea_level/`，四阶段各保留一个公开提交。该范围包含对应代码、配置、测试、许可与说明；生成产物、数据集、环境，以及私有历史与参考文件继续按下述边界处理。指示来源见 `docs/work/2026-09-12-input-stages-closeout/decisions.md` 的U13、U14。

2026-09-17，yZz确认汇聚带抬升工作完成，明确要求更新current与项目文档、按项目规则提交并推送至现有Main。该指示覆盖 `pipline/convergent_uplift/` 的源码、源内设计配置、测试与说明，以及本轮台账、策略和发布范围更新。模块原始资料、拟合参数包、数组、图像、检查产物与运行清单按生成产物规则排除；背景场、其他活动及无关工作不纳入本次新增公开范围。来源见 `docs/work/2026-09-17-convergent-uplift-closeout/decisions.md` U1。远端实际分支名为main，沿用public到origin/main的映射。

公开路径清单保存在 `project-rules/public-paths.txt`。文件名表示该文件，末尾带 `/` 的路径表示整个目录。当前清单为：

- `.gitattributes`
- `.gitignore`
- `README.md`
- `launch_terrain_viewer.bat`
- `pyproject.toml`
- `AGENTS.md`
- `CLAUDE.md`
- `current.md`
- `final-strategy.md`
- `final-strategy/`
- `project-rules/`
- `scripts/`
- `src/`
- `tests/`
- `bench/`，包括已批准公开的脚本、日志与文本结果；生成数组、图片和存储目录按 `.gitignore` 排除。
- `pipline/mask_generator/`
- `pipline/seafloor_generator/`
- `pipline/initial_bathymetry/`
- `pipline/sea_level/`
- `pipline/convergent_uplift/`

`docs/`（包括历史会话、旧计划、研究过程与运行记录）和 `references/` 保留在 `private`。`datasets/`、`output/`、环境与缓存按 `.gitignore` 排除。公开文件中对本地材料的路径引用只保留来源定位，不使被引用的文件进入公开范围；这些引用在公开副本中可能无法访问。用户原话与来源定位保持原文。

新增公开文件、公开文案或扩大范围需要 yZz 明确批准。

## 4. 发布限制

1. 只允许 `refs/heads/public` 推送到 `refs/heads/main`。
2. 禁止推送 `private`、其他分支、tag 或全部 refs。
3. 禁止使用 `git push --all`、`git push --mirror` 和绕过 pre-push 检查的参数。
4. 推送前检查待发送提交的文件树和提交历史。
5. 检查待发送的每个提交的完整文件树；出现公开清单之外的文件时停止推送并报告。公开文件内的本地路径引用按第 3 节处理。
6. 禁止合并、推送或以其他方式使 `private` 独有的提交历史进入公开远端。公开提交以已有 `public` 提交为父提交，从已提交的 `private` 快照中选取公开文件。

版本化检查脚本为 `project-rules/pre-push`，安装到本地 `.git/hooks/pre-push` 后检查远端名、ref 映射、快进关系和待发送历史的文件树。检查使用待推送提交中的 `project-rules/public-paths.txt`。`.gitattributes` 固定这两个文件使用 LF 换行。不得通过关闭或绕过 hook 发布。

## 5. 单工作目录发布流程

1. 核对现有修改与后台写入。在 `private` 提交本次工作快照，记录用于发布的提交号。保留与本次发布无关的修改；后台后来产生的文件留到下一次提交。
2. 按 yZz 当前指令确定本次公开范围和文本。用户已明确要求公开并推送指定文件时，使用其当前内容；不重复请求同一范围的批准。新增范围须更新第 3 节和公开路径清单。
3. 核对 `origin/main` 与本地 `public`。正常发布只作快进推送。
4. 首选在同一 `.git` 中使用临时 `GIT_INDEX_FILE`：由已提交的 `private` 快照读取文件树，只保留公开路径，检查差异后用 `git write-tree` 与 `git commit-tree` 创建以当前 `public` 为唯一父提交的公开提交。用带旧提交号校验的 `git update-ref` 更新 `public`。当前工作目录、当前分支与常规索引保持在 `private`；不创建第二个仓库或 linked worktree。
5. 对照公开清单和来源快照，核对公开提交的路径、文件内容、父提交与待发送历史。同步安装并测试 pre-push 检查。
6. 执行普通 `git push origin`。本地 refspec 和 pre-push 检查只允许 `public` 到 `origin/main`。
7. 用远端查询确认 `origin/main` 等于本地 `public`，并复核当前分支和工作树状态。

没有后台任务且工作树为空时，也可以在同一工作目录切换到 `public`，只取回公开清单中的路径并提交，推送后切回 `private`。`private` 独有文件会在切换期间暂时移除，因此使用前必须确认没有任务依赖这些文件。

## 6. 提交身份

提交沿用仓库现有的 yZz 身份。不得添加 Agent 共同作者、Agent 提交作者或 Contributors 署名。
