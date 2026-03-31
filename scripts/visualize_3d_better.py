import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource

# === 先生成一个更大更细的地形 ===
from landlab import RasterModelGrid
from landlab.components import FlowAccumulator, FastscapeEroder, LinearDiffuser

np.random.seed(42)
grid = RasterModelGrid((256, 256), xy_spacing=50.0)  # 256x256, 50m间距
grid.set_closed_boundaries_at_grid_edges(True, True, True, False)  # 只留一个出水口

z = grid.add_zeros('topographic__elevation', at='node')
z += np.random.uniform(0, 1, z.shape)

fa = FlowAccumulator(grid, flow_director='FlowDirectorD8')
sp = FastscapeEroder(grid, K_sp=1e-5, m_sp=0.5, n_sp=1.0)
ld = LinearDiffuser(grid, linear_diffusivity=0.01)

dt = 1000
for i in range(500):
    z[grid.core_nodes] += 0.001 * dt  # 1mm/yr 抬升
    fa.run_one_step()
    sp.run_one_step(dt)
    ld.run_one_step(dt)

elevation = grid.at_node['topographic__elevation'].reshape(grid.shape)
np.save('/mnt/f/LEM/output/elevation_256.npy', elevation)
print(f"Generated: {elevation.shape}, range {elevation.min():.1f} ~ {elevation.max():.1f} m")

# === 画好看的 3D 图 ===
nrows, ncols = elevation.shape
x = np.arange(ncols) * 50
y = np.arange(nrows) * 50
X, Y = np.meshgrid(x, y)

# 用光照效果让地形更立体
ls = LightSource(azdeg=315, altdeg=35)

fig = plt.figure(figsize=(16, 12))

# 大图：3D 视图，带光照
ax1 = fig.add_subplot(221, projection='3d')
ax1.plot_surface(X, Y, elevation, cmap='terrain',
                 linewidth=0, antialiased=True,
                 rstride=1, cstride=1)
ax1.set_xlabel('X (m)')
ax1.set_ylabel('Y (m)')
ax1.set_zlabel('Elevation (m)')
ax1.set_title('3D Terrain (side view)')
ax1.view_init(elev=30, azim=225)

# 换个角度
ax2 = fig.add_subplot(222, projection='3d')
ax2.plot_surface(X, Y, elevation, cmap='terrain',
                 linewidth=0, antialiased=True,
                 rstride=1, cstride=1)
ax2.set_xlabel('X (m)')
ax2.set_ylabel('Y (m)')
ax2.set_zlabel('Elevation (m)')
ax2.set_title('3D Terrain (bird view)')
ax2.view_init(elev=55, azim=270)

# 带光影的俯视图（像卫星图一样）
rgb = ls.shade(elevation, cmap=plt.cm.terrain, vert_exag=2, blend_mode='soft')
ax3 = fig.add_subplot(223)
ax3.imshow(rgb, origin='lower')
ax3.set_title('Hillshade (like satellite view)')
ax3.set_xlabel('X')
ax3.set_ylabel('Y')

# 纯高度图
ax4 = fig.add_subplot(224)
im = ax4.imshow(elevation, cmap='terrain', origin='lower')
ax4.set_title('Heightmap (color = elevation)')
ax4.set_xlabel('X')
ax4.set_ylabel('Y')
plt.colorbar(im, ax=ax4, label='Elevation (m)')

plt.tight_layout()
plt.savefig('/mnt/f/LEM/output/terrain_3d_better.png', dpi=200)
plt.close()
print("Saved to /mnt/f/LEM/output/terrain_3d_better.png")
