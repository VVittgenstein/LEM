
import argparse as _experiment_argparse
from pathlib import Path
_experiment_root = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
_experiment_parser = _experiment_argparse.ArgumentParser()
_experiment_parser.add_argument('--output', type=Path, default=_experiment_root / 'output')
_experiment_output = _experiment_parser.parse_args().output.resolve()
_experiment_output.mkdir(parents=True, exist_ok=True)

import numpy as np
import matplotlib.pyplot as plt

# 加载数据
elevation = np.load(str(_experiment_output / 'final_elevation.npy'))

# 创建坐标网格（100x100，间距 100m）
nrows, ncols = elevation.shape
x = np.arange(ncols) * 100  # 米
y = np.arange(nrows) * 100
X, Y = np.meshgrid(x, y)

fig = plt.figure(figsize=(14, 5))

# 左：3D 表面图
ax1 = fig.add_subplot(121, projection='3d')
ax1.plot_surface(X, Y, elevation, cmap='terrain', linewidth=0, antialiased=True)
ax1.set_xlabel('X (m)')
ax1.set_ylabel('Y (m)')
ax1.set_zlabel('Elevation (m)')
ax1.set_title('3D Terrain View')
ax1.view_init(elev=35, azim=225)

# 右：俯视高度图（对比）
ax2 = fig.add_subplot(122)
im = ax2.imshow(elevation, cmap='terrain', origin='lower')
ax2.set_title('Top-down Heightmap')
ax2.set_xlabel('X')
ax2.set_ylabel('Y')
plt.colorbar(im, ax=ax2, label='Elevation (m)')

plt.tight_layout()
plt.savefig(str(_experiment_output / 'terrain_3d.png'), dpi=150)
plt.close()

print(f"Grid size: {nrows}x{ncols}")
print(f"Elevation range: {elevation.min():.1f} ~ {elevation.max():.1f} m")
print(f"Outputs: {_experiment_output}")
