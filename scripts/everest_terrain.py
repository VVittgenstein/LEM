import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from landlab import RasterModelGrid
from landlab.components import FlowAccumulator, FastscapeEroder, LinearDiffuser
import time

print("Setting up 2048x2048 grid...")
np.random.seed(777)
grid = RasterModelGrid((2048, 2048), xy_spacing=30.0)  # 30m spacing → ~61km x 61km

z = grid.add_zeros('topographic__elevation', at='node')
z += np.random.uniform(0, 2, z.shape)

fa = FlowAccumulator(grid, flow_director='FlowDirectorD8')
sp = FastscapeEroder(grid, K_sp=2e-5, m_sp=0.5, n_sp=1.0)
ld = LinearDiffuser(grid, linear_diffusivity=0.005)  # very low → sharp ridges

dt = 2000
uplift = 0.005  # 5mm/yr — Himalayan uplift rate
n_steps = 400

print(f"Running {n_steps} steps (total sim time: {n_steps*dt/1e6:.1f} Myr)...")
t0 = time.time()
for i in range(n_steps):
    z[grid.core_nodes] += uplift * dt
    fa.run_one_step()
    sp.run_one_step(dt)
    ld.run_one_step(dt)
    if (i+1) % 50 == 0:
        elapsed = time.time() - t0
        elev = z.reshape(grid.shape)
        print(f"  Step {i+1}/{n_steps} ({elapsed:.0f}s) — "
              f"range: {elev.min():.0f}~{elev.max():.0f}m")

elapsed = time.time() - t0
print(f"Done in {elapsed:.0f}s")

elevation = grid.at_node['topographic__elevation'].reshape(grid.shape)
np.save('/mnt/f/LEM/output/elevation_2048_everest.npy', elevation)
print(f"Shape: {elevation.shape}")
print(f"Range: {elevation.min():.0f} ~ {elevation.max():.0f} m")
print(f"Mean: {elevation.mean():.0f} m")

# === Visualization ===
print("Rendering...")
nrows, ncols = elevation.shape
ls = LightSource(azdeg=315, altdeg=35)

fig = plt.figure(figsize=(20, 16))

# 3D side view (subsample for rendering speed)
step = 8  # render every 8th point
x = np.arange(0, ncols, step) * 30
y = np.arange(0, nrows, step) * 30
X, Y = np.meshgrid(x, y)
elev_sub = elevation[::step, ::step]

ax1 = fig.add_subplot(221, projection='3d')
ax1.plot_surface(X, Y, elev_sub, cmap='terrain',
                 linewidth=0, antialiased=True, rstride=1, cstride=1)
ax1.set_title('3D Side View', fontsize=15)
ax1.view_init(elev=25, azim=230)
ax1.set_box_aspect([1, 1, 0.5])

# 3D low angle
ax2 = fig.add_subplot(222, projection='3d')
ax2.plot_surface(X, Y, elev_sub, cmap='terrain',
                 linewidth=0, antialiased=True, rstride=1, cstride=1)
ax2.set_title('3D Low Angle', fontsize=15)
ax2.view_init(elev=10, azim=200)
ax2.set_box_aspect([1, 1, 0.5])

# Hillshade
rgb = ls.shade(elevation, cmap=plt.cm.terrain, vert_exag=2, blend_mode='soft')
ax3 = fig.add_subplot(223)
ax3.imshow(rgb, origin='lower')
ax3.set_title('Hillshade (satellite view)', fontsize=15)
ax3.set_xticks([])
ax3.set_yticks([])

# Heightmap
ax4 = fig.add_subplot(224)
im = ax4.imshow(elevation, cmap='terrain', origin='lower')
ax4.set_title('Heightmap', fontsize=15)
ax4.set_xticks([])
ax4.set_yticks([])
plt.colorbar(im, ax=ax4, label='Elevation (m)', shrink=0.8)

plt.suptitle(f'Everest-style Terrain: 2048x2048, 30m spacing\n'
             f'Relief: {elevation.max():.0f}m | '
             f'K={2e-5}, D=0.005, uplift=5mm/yr, {n_steps*dt/1e6:.1f} Myr',
             fontsize=16, y=0.99)
plt.tight_layout()
plt.savefig('/mnt/f/LEM/output/terrain_everest.png', dpi=200)
plt.close()
print("Saved: /mnt/f/LEM/output/terrain_everest.png")
