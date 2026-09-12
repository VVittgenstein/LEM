# 上游来源与改造记录

本模块的分区生长、随机数和 Simplex 噪声部分参考并改编自：

- 项目：World Orogen，`raguilar011095/planet_heightmap_generation`
- 固定提交：`cc2662b4edd52231c4f65d8765f3ef12cd82d9b7`
- 来源：[固定版本仓库](https://github.com/raguilar011095/planet_heightmap_generation/tree/cc2662b4edd52231c4f65d8765f3ef12cd82d9b7)
- 上游许可证：GNU General Public License version 3，文本保存在本目录 `LICENSE`。

| 本地文件 | 参考的上游文件 | 改动 |
| --- | --- | --- |
| `noise.py` | `js/rng.js`、`js/simplex-noise.js` | Park-Miller 随机数与 3D Simplex 噪声的 Python/NumPy 实现；已与原始代码的固定数值核对 |
| `partitions.py` | `js/plates.js`、`js/coarse-plates.js`、`js/sphere-mesh.js`、`js/terrain-config.js` | 平面抖动点及 Delaunay 邻接图；二维方向与距离；平方距离和等面积半径比较；种子连通分区整理；边界与种子附近的投影位移衰减 |

`selection.py` 实现当前对话确认的统一顺序随机选择公式，替换上游 `ocean-land.js` 中多陆块组扩展和内部海域吸收的逻辑。全部候选采用相同评分规则，无形态类别配额。

上游保存位置及逐文件哈希见项目的 `references/2026-09-10-platform-shape-methods/source-manifest.json`。本次输出清单还记录运行所用代码、上游文件与输出文件的 SHA-256。
