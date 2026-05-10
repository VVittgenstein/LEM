# LEM-Diffusion / LEM-Diffusion 地形生成项目

## 项目目标 / Project Goal

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

## 为什么做这个 / Why This Exists

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

## 当前状态 / Current Status

**中文**

项目目前处在 Phase 1：数据管线工程化和工具建设。

已经完成的基础工作：

- 梳理了 Terrain Diffusion、InfiniteDiffusion、Laplacian 编码和 Veloren
  worldgen 相关资料。
- 已有 Landlab 风格的 LEM 实验脚本和地形可视化脚本。
- 已实现一个辅助工具 LEM Terrain Viewer，用于交互式检查 `.npy` 地形输出。

下一步主线工作是：构建可重复的多通道 LEM 数据生成管线，实现可逆 Laplacian
Pyramid 编码，定义轻量数据 schema，并训练一个小型端到端 diffusion prototype。

**English**

The project is currently in Phase 1: data-pipeline engineering and tooling.

Completed groundwork:

- Terrain Diffusion, InfiniteDiffusion, Laplacian encoding, and Veloren
  worldgen references have been reviewed and distilled.
- Landlab-style LEM experiments and terrain visualization scripts exist.
- A side tool, LEM Terrain Viewer, has been implemented to inspect `.npy`
  terrain outputs interactively.

The next mainline work is to build a repeatable multi-channel LEM data
generation pipeline, implement reversible Laplacian Pyramid encoding, define a
lightweight dataset schema, and train a small end-to-end diffusion prototype.

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
README.md
pyproject.toml
launch_terrain_viewer.bat
scripts/
  lem_demo.py             # early LEM demo
  everest_terrain.py      # terrain experiment scripts
  visualize_3d*.py        # exploratory visualization scripts
  launch_terrain_viewer.pyw

src/lem_viewer/
  app.py                  # application orchestration and plugin discovery
  main.py                 # CLI entry point
  models.py               # TerrainDataset, TerrainChannel, statistics
  registry.py             # loader/channel/view plugin registry
  loaders/                # .npy loader plus HDF5/Zarr extension stubs
  channels/               # derived channel providers
  views/                  # 3D surface and compare views
  ui/                     # PySide6 main window and controls

tests/viewer/             # viewer tests and launcher smoke coverage
```

## 地形查看器 / Terrain Viewer

**中文**

Terrain Viewer 是当前可用的辅助工具，用来检查生成出来的地形数组质量。它不
是最终产品，但在主数据管线搭建过程中很有用。

当前支持：

- 加载单个 `.npy` 地形数组。
- 加载一个目录中的多个同 shape `.npy` 文件作为不同通道。
- 交互式 3D OpenGL 地形表面。
- 当存在 `elevation` 通道时，自动生成 `slope` 和 `hillshade` 派生通道。
- 双视图 3D 对比，并同步相机。
- 对大网格做显示降采样，同时在数据模型中保留原始数组。
- Windows 启动器可自动创建 repo-local 的 `lem-env-win` 并安装 viewer 依赖。

**English**

Terrain Viewer is the currently usable inspection tool for generated terrain
arrays. It is not the final product, but it is useful while the main data
pipeline is being built.

It currently supports:

- Loading a single `.npy` terrain array.
- Loading a directory of same-shaped `.npy` files as named channels.
- Interactive 3D OpenGL terrain surfaces.
- Derived `slope` and `hillshade` channels when `elevation` exists.
- Side-by-side 3D comparison with synchronized cameras.
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

Run the viewer test suite:

```powershell
python -m pytest
```

**中文**

测试覆盖 plugin discovery、`.npy` 加载、派生通道、Qt smoke behavior、
端到端 UI 数据绑定，以及 Windows launcher bootstrap。

**English**

The tests cover plugin discovery, `.npy` loading, derived channels, Qt smoke
behavior, end-to-end data binding, and Windows launcher bootstrap behavior.
