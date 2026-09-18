# LEM-Diffusion / LEM-Diffusion 地形生成项目

当前项目计划以 [`final-strategy/README.md`](final-strategy/README.md) 为入口，任务与阶段进展见 [`current.md`](current.md)，项目协作规则见 [`AGENTS.md`](AGENTS.md) 和 [`project-rules/`](project-rules)。以下内容包含项目早期概述；当前范围与状态以最终策略和台账为准。计划与台账中的部分来源保存在本地会话或参考材料中，公开仓库不包含这些来源全文。

## 当前状态 / Current Status

2026-09-18，yZz确认**全仓代码结构与存储位置修复**和**3D体素查看器合并**两项工程任务均已完成。任务与完成依据见 [T-011](current.md#t-011)、[T-012](current.md#t-012)；当前查看器说明见 [viewer/README.md](viewer/README.md)。其他研究、数据生成与训练任务沿用下述状态。

已合并的查看器提供两个独立显示位，可分别选择二维地图、三维表面或三维体素，也可关闭其中一个并从菜单恢复。C++体素高度级数可调，垂直放大为1时采用统一物理尺度；普通数值框、焦点恢复、图例布局及Fly滚轮缩放等本轮交互调整已纳入完成范围。使用、构建和验证说明见 [viewer/README.md](viewer/README.md)。

2026-09-12，yZz确认 **数据4（初始台地二维形状）与数据1（初始海底高程和海平面）已完成并验收**。当前成果按四阶段组织：

| 阶段 | 代码与说明 | 入口 |
|---|---|---|
| 台地掩膜 | [mask_generator](data_generation/stage/mask_generator/README.md)，512分区、外围3层禁选，500×500、1 km格距 | `data_generation/stage/mask_generator/run_world_orogen_gibbs.ps1` |
| 深浅海类型分配 | [seafloor_generator](data_generation/stage/seafloor_generator/README.md)，四个拟合函数与完整地块组合 | `data_generation/stage/seafloor_generator/run.ps1` |
| 初始海底 | [initial_bathymetry](data_generation/stage/initial_bathymetry/README.md)，固定剖面、相关起伏、等高线和剖面图 | `data_generation/stage/initial_bathymetry/run.ps1` |
| 海平面 | [sea_level](data_generation/stage/sea_level/README.md)，4800万年至现代的单一年代曲线和SVG | `data_generation/stage/sea_level/run.ps1` |

生成文件及原数据按 `.gitignore` 保留在本地，各模块说明记录输入、产物路径和哈希。台地面积50%至60%为软偏好，34个陆块作形状参考。初始高程为全域水下，模拟窗口海平面起点为0 m。

2026-09-17，yZz确认 **数据2中的汇聚带抬升子管线已完成并验收**。每次触发创建完整独立事件，空间形态、作用位置、强度场和连续生命周期一起确定。已交付8个数据域的13个独立事件及各自A至E图，包含97个时刻画面。入口为 [convergent_uplift](data_generation/stage/convergent_uplift/README.md)，时间与事件入口为 `data_generation/stage/convergent_uplift/run_time.ps1`；接口提供m/yr速率与m累计位移。案例代理和设计参数的依据身份随模块说明保留。

下一范围为数据2其余活动、数据3、数据5、统一LEM驱动接入及终态验证。完整1A、E1、模型训练和LOD验证保持各自状态。当前策略入口见 [已验收输入阶段](final-strategy/architecture-dataflow.md#initial-input-stages)。

The initial platform-mask input (data class 4) and initial bathymetry and sea-level inputs (data class 1) were accepted on 2026-09-12. The four modules above provide their code, data contracts and local validation records. The convergent-uplift input pipeline was accepted on 2026-09-17. Each trigger creates an independent event with its own spatial field, placement and lifecycle. The delivered batch contains 13 events across eight domains. Remaining activity types, other input classes, LEM integration and end-state validation continue separately.

## 早期项目概述 / Early Project Overview

**中文**

LEM-Diffusion 是一个早期地形生成项目。核心想法是：先用 Landscape
Evolution Model（LEM，地貌演化模型）生成物理上更可信的地形训练数据，
再训练 diffusion model，让模型能够快速、分块地生成适合游戏使用的地形。

长期目标是做出一个 Minecraft Java Edition 地形生成模组。这个模组不只是
生成普通高度图，而是希望利用 cascade diffusion model 的多级输出，直接
对接游戏里的 LOD 系统。计划中的 MVP 是 Forge + Distant Horizons，后续
Phase 2 再考虑 Fabric + Voxy。

**English**

LEM-Diffusion is an early-stage terrain generation project. The core idea is to
use Landscape Evolution Models (LEMs) to generate physically plausible terrain
training data, then train diffusion models that can produce fast, tiled terrain
for games.

The long-term target is a Minecraft Java Edition terrain-generation mod. Rather
than only producing a plain heightmap, the project aims to use the multi-level
outputs of a cascade diffusion model as native LOD data. The planned MVP is a
Forge + Distant Horizons integration, followed later by a Fabric + Voxy phase.

## 早期动机与概念 / Early Motivation

**中文**

传统 LEM 很适合生成具有侵蚀、水系和大尺度地形结构的自然地貌，但它不适合
直接分块运行，因为水文和侵蚀过程依赖全局地形信息。游戏地形生成则刚好需
要相反的能力：快速、局部、可随机访问，并且常常需要多级 LOD。

这个项目要解决的就是两者之间的断层：

1. 用 Landlab / Fastscape 这类 LEM 工具生成物理上合理的训练数据。
2. 先训练小型 diffusion model，跑通 heightmap 和相关通道的生成。
3. 再推进 conditional、多通道和 cascade 生成。
4. 最终把 cascade 结构本身作为游戏 LOD 数据来使用。

关键架构洞察是：cascade diffusion 的层级和游戏 LOD 层级天然同构。低分辨率
全局地形负责世界级一致性，高分辨率 tile 负责局部细节。

**English**

Traditional LEM simulation is good at producing coherent erosion, drainage, and
large-scale terrain structure, but it is not naturally tileable because
hydrology and erosion depend on global context. Game terrain generation needs
the opposite property: fast, local, randomly accessible generation, often at
multiple levels of detail.

This project explores the bridge between those constraints:

1. Generate physically grounded terrain datasets with Landlab/Fastscape-style
   LEM pipelines.
2. Train a small diffusion model on heightmaps and related terrain channels.
3. Move toward conditional, multi-channel, and cascade generation.
4. Use the cascade structure itself as native LOD data for game integration.

The key architectural insight is that cascade diffusion levels and game LOD
levels are structurally aligned. Low-resolution global terrain provides
world-scale coherence, while higher-resolution tiles add local detail.


## 路线图 / Roadmap

```text
Phase 1: LEM data generation with Landlab/Fastscape
Phase 2: Small unconditional diffusion model
Phase 3: Conditional terrain generation
Phase 4: Multi-channel terrain generation
Phase 5: Tiled/cascade generation
Phase 6: Minecraft Java mod integration with native LOD output
```

**中文**

当前优先级是先把多通道数据生成和训练闭环跑通，再考虑更复杂的特征工程。

**English**

The current priority is to make the multi-channel data generation and training
loop work before doing heavier feature engineering.

## 仓库结构 / Repository Layout

```text
data_generation/
  stage/                    当前六个数据生成阶段
  pipeline/                 后续完整集成实现的预留目录
experiments/                旧完整流程、Landlab 实验与 Fastscape 示例
references/                 外部参考资料及来源索引
  data/                     参考数据与派生参考资料
  paper/                    论文、补充材料和书目信息
  code/                     外部参考实现及配套资料
datasets/                   模型训练数据集
viewer/
  lem_viewer/               查看器 Python 包
  scripts/                  查看器启动辅助
  experiments/              早期绘图程序
training/                   后续训练实现的预留目录
tests/
  viewer/
  data_generation/stage/
  benchmarks/
  run.py                    跨环境集中测试入口
bench/results/              已有基准结果与报告
launch_terrain_viewer.bat    Windows 查看器入口
final-strategy/             项目最终策略
project-rules/              协作与发布规则
```

目录入口：[数据生成](data_generation/README.md)、[实验与旧流程](experiments/README.md)、[参考资料](references/README.md)、[训练数据集](datasets/README.md)、[查看器](viewer/README.md)、[训练](training/README.md)、[测试](tests/README.md)。阶段的具体实现与后续完整管线分开组织；完整管线运行须独立于 stage 的代码。datasets 位于项目根目录，与 references 平级，专用于模型训练数据。

## 地形查看器 / Terrain Viewer

**中文**

Terrain Viewer 是当前可用的辅助工具，用来检查生成出来的地形数组质量。它不
是最终产品，但在主数据管线搭建过程中很有用。

当前支持：

- 加载单个 `.npy` 地形数组。
- 加载分支查看器的 `.flem` v1 文件。
- 加载一个目录中的多个同 shape `.npy` 文件作为不同通道。
- 交互式 3D OpenGL 地形表面。
- 当存在 `elevation` 通道时，自动生成 `slope` 和 `hillshade` 派生通道。
- 两个显示位分别选择二维地图、三维表面或三维体素；两个表面视图可同步相机。
- C++ 体素视图支持可调高度级数、物理尺度、水位、材质外观、环绕与飞行相机。
- 对大网格做显示降采样，同时在数据模型中保留原始数组。
- Windows 启动器可自动创建 repo-local 的 `lem-env-win` 并安装 viewer 依赖。

**English**

Terrain Viewer is the currently usable inspection tool for generated terrain
arrays. It is not the final product, but it is useful while the main data
pipeline is being built.

It currently supports:

- Loading a single `.npy` terrain array.
- Loading `.flem` v1 files from the branch viewer.
- Loading a directory of same-shaped `.npy` files as named channels.
- Interactive 3D OpenGL terrain surfaces.
- Derived `slope` and `hillshade` channels when `elevation` exists.
- Two independently selectable map, surface, or voxel displays; surface pairs can synchronize cameras.
- A C++ voxel renderer with adjustable height precision, physical scale, water level, material appearance, and orbit/fly cameras.
- Display downsampling for large grids while preserving original arrays in the
  data model.
- A Windows launcher that creates a repo-local `lem-env-win` environment and
  installs viewer dependencies if needed.

## 依赖 / Requirements

- Python 3.12+
- `numpy`
- `PySide6`
- `pyqtgraph`
- `PyOpenGL`

**中文**

Viewer 依赖声明在 `pyproject.toml` 中。HDF5 和 Zarr 目前只是预留 loader
接口，还不是完整的数据读取实现。

**English**

Viewer dependencies are declared in `pyproject.toml`. HDF5 and Zarr currently
exist as loader extension stubs, not complete data readers.

## 安装 / Install

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

For test dependencies:

```powershell
python -m pip install -e ".[test]"
```

## 运行查看器 / Run The Viewer

Open with no initial source:

```powershell
lem-viewer
```

Open a single `.npy` file:

```powershell
lem-viewer output\elevation.npy
```

Open a directory of `.npy` channels:

```powershell
lem-viewer output\
```

On Windows, double-click:

```text
launch_terrain_viewer.bat
```

**中文**

如果启动失败，Windows launcher 会保留控制台窗口，方便读取依赖或环境错误。

**English**

If startup fails, the Windows launcher keeps the console open so dependency or
environment errors are readable.

## 数据约定 / Data Expectations

**中文**

当前实现的 `.npy` loader 期望输入是 2D 数组：

- 如果有长度为 1 的多余维度，会尽可能 squeeze 成 2D。
- 单个文件会变成一个通道，通道名来自文件名 stem。
- 目录会把其中每个 `.npy` 文件加载成一个通道。
- 同一个目录数据集里的所有数组必须有相同的 2D shape。
- 如果存在 `elevation` 通道，会自动计算 `slope` 和 `hillshade`。

**English**

The implemented `.npy` loader expects 2D arrays:

- Length-1 dimensions are squeezed when possible.
- A single file becomes one channel named after the file stem.
- A directory loads every `.npy` file as a channel.
- All arrays in a directory dataset must share the same 2D shape.
- If an `elevation` channel exists, `slope` and `hillshade` are computed
  automatically.

## 测试 / Tests

Run all default groups in their configured environments:

```powershell
.\lem-env-win\Scripts\python.exe tests\run.py
```

Use `--list` to inspect groups and `--group viewer` to select the viewer suite.
The repository-level `python -m pytest` command collects viewer tests only.
Environment selection, data-dependent checks and explicit numerical experiments are described in [tests/README.md](tests/README.md).
