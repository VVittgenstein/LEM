import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from landlab import RasterModelGrid
from landlab.components import FlowAccumulator, FastscapeEroder, LinearDiffuser

np.random.seed(12345)
grid = RasterModelGrid((256, 256), xy_spacing=50.0)

# 四周都是开放边界（水可以从任何边缘流出）
z = grid.add_zeros('topographic__elevation', at='node')
z += np.random.uniform(0, 1, z.shape)

fa = FlowAccumulator(grid, flow_director='FlowDirectorD8')
sp = FastscapeEroder(grid, K_sp=3e-5, m_sp=0.5, n_sp=1.0)
ld = LinearDiffuser(grid, linear_diffusivity=0.05)

dt = 1000
for i in range(800):
    z[grid.core_nodes] += 0.0015 * dt
    fa.run_one_step()
    sp.run_one_step(dt)
    ld.run_one_step(dt)

elevation = grid.at_node['topographic__elevation'].reshape(grid.shape)
np.save('/mnt/f/LEM/output/elevation_256_v3.npy', elevation)
print(f"Shape: {elevation.shape}")
print(f"Range: {elevation.min():.1f} ~ {elevation.max():.1f} m")
print(f"Mean: {elevation.mean():.1f} m, Std: {elevation.std():.1f} m")

# === 可视化 ===
nrows, ncols = elevation.shape
x = np.arange(ncols) * 50
y = np.arange(nrows) * 50
X, Y = np.meshgrid(x, y)
ls = LightSource(azdeg=315, altdeg=35)

fig = plt.figure(figsize=(18, 14))

# 3D 侧视
ax1 = fig.add_subplot(221, projection='3d')
ax1.plot_surface(X, Y, elevation, cmap='terrain',
                 linewidth=0, antialiased=True, rstride=2, cstride=2)
ax1.set_title('3D Side View', fontsize=14)
ax1.view_init(elev=25, azim=230)
ax1.set_box_aspect([1, 1, 0.4])

# 3D 低角度（像站在地面看）
ax2 = fig.add_subplot(222, projection='3d')
ax2.plot_surface(X, Y, elevation, cmap='terrain',
                 linewidth=0, antialiased=True, rstride=2, cstride=2)
ax2.set_title('3D Low Angle', fontsize=14)
ax2.view_init(elev=12, azim=200)
ax2.set_box_aspect([1, 1, 0.4])

# 带光影的俯视图
rgb = ls.shade(elevation, cmap=plt.cm.terrain, vert_exag=3, blend_mode='soft')
ax3 = fig.add_subplot(223)
ax3.imshow(rgb, origin='lower', extent=[0, ncols*50, 0, nrows*50])
ax3.set_title('Hillshade (satellite view)', fontsize=14)
ax3.set_xlabel('X (m)')
ax3.set_ylabel('Y (m)')

# 高度图
ax4 = fig.add_subplot(224)
im = ax4.imshow(elevation, cmap='terrain', origin='lower',
                extent=[0, ncols*50, 0, nrows*50])
ax4.set_title('Heightmap', fontsize=14)
ax4.set_xlabel('X (m)')
ax4.set_ylabel('Y (m)')
plt.colorbar(im, ax=ax4, label='Elevation (m)', shrink=0.8)

plt.suptitle('Landlab Terrain: 256x256, 50m spacing, 800kyr simulation',
             fontsize=16, y=0.98)
plt.tight_layout()
plt.savefig('/mnt/f/LEM/output/terrain_3d_v3.png', dpi=200)
plt.close()
print("Saved: /mnt/f/LEM/output/terrain_3d_v3.png")
