import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from landlab import RasterModelGrid
from landlab.components import FlowAccumulator, FastscapeEroder, LinearDiffuser

def run_lem(K_sp, D, uplift, label, seed=42):
    """Run one LEM simulation and return elevation grid."""
    np.random.seed(seed)
    grid = RasterModelGrid((128, 128), xy_spacing=50.0)
    z = grid.add_zeros('topographic__elevation', at='node')
    z += np.random.uniform(0, 1, z.shape)

    fa = FlowAccumulator(grid, flow_director='FlowDirectorD8')
    sp = FastscapeEroder(grid, K_sp=K_sp, m_sp=0.5, n_sp=1.0)
    ld = LinearDiffuser(grid, linear_diffusivity=D)

    dt = 1000
    for i in range(500):
        z[grid.core_nodes] += uplift * dt
        fa.run_one_step()
        sp.run_one_step(dt)
        ld.run_one_step(dt)

    elev = grid.at_node['topographic__elevation'].reshape(grid.shape)
    print(f"{label}: range {elev.min():.0f}~{elev.max():.0f}m, mean={elev.mean():.0f}m")
    return elev

ls = LightSource(azdeg=315, altdeg=35)

# ============================================
# 实验1：改变侵蚀系数 K（其他固定）
# ============================================
fig, axes = plt.subplots(2, 3, figsize=(18, 12))

configs_K = [
    (1e-6, 0.01, 0.001, "K=very small\n(erosion weak, tall mountains)"),
    (1e-5, 0.01, 0.001, "K=small\n(moderate erosion)"),
    (1e-4, 0.01, 0.001, "K=large\n(erosion strong, flat terrain)"),
]

for i, (K, D, U, label) in enumerate(configs_K):
    elev = run_lem(K, D, U, label)
    rgb = ls.shade(elev, cmap=plt.cm.terrain, vert_exag=3, blend_mode='soft')
    axes[0][i].imshow(rgb, origin='lower')
    axes[0][i].set_title(label, fontsize=13)
    axes[0][i].set_xticks([])
    axes[0][i].set_yticks([])

# ============================================
# 实验2：改变扩散系数 D（其他固定）
# ============================================
configs_D = [
    (3e-5, 0.001, 0.001, "D=very small\n(sharp ridges)"),
    (3e-5, 0.05, 0.001,  "D=medium\n(smooth hills)"),
    (3e-5, 0.5, 0.001,   "D=large\n(very rounded)"),
]

for i, (K, D, U, label) in enumerate(configs_D):
    elev = run_lem(K, D, U, label)
    rgb = ls.shade(elev, cmap=plt.cm.terrain, vert_exag=3, blend_mode='soft')
    axes[1][i].imshow(rgb, origin='lower')
    axes[1][i].set_title(label, fontsize=13)
    axes[1][i].set_xticks([])
    axes[1][i].set_yticks([])

axes[0][0].set_ylabel('Change K\n(erosion strength)', fontsize=14, fontweight='bold')
axes[1][0].set_ylabel('Change D\n(smoothing strength)', fontsize=14, fontweight='bold')

plt.suptitle('What do the parameters do?', fontsize=18, y=0.98)
plt.tight_layout()
plt.savefig('/mnt/f/LEM/output/param_comparison.png', dpi=180)
plt.close()
print("\nSaved: /mnt/f/LEM/output/param_comparison.png")
