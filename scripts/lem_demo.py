"""
LEM Demo: 使用 Landlab 进行基础地形侵蚀模拟
==============================================

这个脚本演示了一个简单的地貌演化模型 (Landscape Evolution Model):
- 创建一个 100x100 的网格地形
- 施加均匀抬升 (uniform uplift)
- 使用 stream power 侵蚀模型模拟河流侵蚀
- 使用线性扩散模型模拟坡面过程 (hillslope diffusion)
- 运行模拟并保存结果

物理过程:
  1. Tectonic uplift: 地壳抬升，提高地表高程
  2. Stream power erosion: 河流沿水流路径侵蚀基岩
  3. Linear diffusion: 模拟坡面上的土壤蠕变和风化搬运
"""

import time
import numpy as np
import matplotlib
matplotlib.use('Agg')  # 无头模式，不需要显示器
import matplotlib.pyplot as plt

# Landlab 核心组件
from landlab import RasterModelGrid
from landlab.components import (
    FlowAccumulator,       # 计算水流方向和汇水面积
    FastscapeEroder,       # Stream power 侵蚀模型 (E = K * A^m * S^n)
    LinearDiffuser,        # 线性扩散（坡面过程）
)

# ============================================================
# 1. 模型参数设置
# ============================================================

# 网格参数
nrows = 100          # 行数
ncols = 100          # 列数
dx = 100.0           # 网格间距 (米)

# 物理参数
uplift_rate = 1e-3          # 抬升速率 (m/yr)，约 1 mm/yr
K_sp = 1e-5                 # Stream power 侵蚀系数 (1/yr)
m_sp = 0.5                  # 汇水面积指数
n_sp = 1.0                  # 坡度指数
D_hs = 0.01                 # 坡面扩散系数 (m^2/yr)

# 时间参数
dt = 1000.0                 # 时间步长 (yr)
total_time = 500_000.0      # 总模拟时间 (yr)，50 万年
n_steps = int(total_time / dt)

print("=" * 60)
print("LEM Demo: Landlab 地形侵蚀模拟")
print("=" * 60)
print(f"网格大小: {nrows} x {ncols}, 间距: {dx} m")
print(f"模拟区域: {nrows * dx / 1000:.1f} km x {ncols * dx / 1000:.1f} km")
print(f"抬升速率: {uplift_rate * 1000:.1f} mm/yr")
print(f"侵蚀系数 K: {K_sp:.1e}")
print(f"扩散系数 D: {D_hs}")
print(f"时间步长: {dt:.0f} yr, 总时间: {total_time/1000:.0f} kyr")
print(f"总步数: {n_steps}")
print()

# ============================================================
# 2. 创建网格并设置初始条件
# ============================================================

print("创建网格和初始地形...")

# 创建 Landlab 光栅网格
grid = RasterModelGrid((nrows, ncols), xy_spacing=dx)

# 添加高程场：初始为随机微小起伏（模拟天然不平整）
np.random.seed(42)
z = grid.add_zeros("topographic__elevation", at="node")
z += np.random.rand(grid.number_of_nodes) * 1.0  # 0~1 米的随机起伏

# 设置边界条件：四边为固定高程（开放边界，允许水流出）
grid.set_closed_boundaries_at_grid_edges(
    right_is_closed=False,
    top_is_closed=False,
    left_is_closed=False,
    bottom_is_closed=False,
)

print(f"初始高程范围: [{z.min():.3f}, {z.max():.3f}] m")

# ============================================================
# 3. 初始化 Landlab 组件
# ============================================================

print("初始化模拟组件...")

# 水流路由器：计算水流方向和汇水面积
fa = FlowAccumulator(grid, flow_director="D8")

# Stream power 侵蚀器：模拟河流侵蚀
sp = FastscapeEroder(grid, K_sp=K_sp, m_sp=m_sp, n_sp=n_sp)

# 线性扩散器：模拟坡面过程
ld = LinearDiffuser(grid, linear_diffusivity=D_hs)

print("组件初始化完成。")
print()

# ============================================================
# 4. 运行模拟主循环
# ============================================================

print("开始运行模拟...")
start_time = time.time()

# 用于记录中间状态的列表
elevation_history = []
record_interval = n_steps // 5  # 每 20% 记录一次

for i in range(n_steps):
    # (a) 施加构造抬升：所有核心节点高程增加
    z[grid.core_nodes] += uplift_rate * dt

    # (b) 计算水流方向和汇水面积
    fa.run_one_step()

    # (c) 河流侵蚀
    sp.run_one_step(dt)

    # (d) 坡面扩散
    ld.run_one_step(dt)

    # 定期记录和报告
    if (i + 1) % record_interval == 0:
        elapsed = time.time() - start_time
        progress = (i + 1) / n_steps * 100
        current_time_kyr = (i + 1) * dt / 1000
        print(f"  进度: {progress:.0f}% | 模拟时间: {current_time_kyr:.0f} kyr | "
              f"高程: [{z.min():.1f}, {z.max():.1f}] m | "
              f"耗时: {elapsed:.1f}s")
        elevation_history.append(z.copy())

end_time = time.time()
run_duration = end_time - start_time

print()
print(f"模拟完成！总耗时: {run_duration:.2f} 秒")
print()

# ============================================================
# 5. 结果统计
# ============================================================

final_elevation = z.reshape((nrows, ncols))

print("=" * 60)
print("最终地形统计:")
print("=" * 60)
print(f"最小高程: {final_elevation.min():.2f} m")
print(f"最大高程: {final_elevation.max():.2f} m")
print(f"平均高程: {final_elevation.mean():.2f} m")
print(f"高程标准差: {final_elevation.std():.2f} m")
print(f"高程范围 (relief): {final_elevation.max() - final_elevation.min():.2f} m")
print()

# ============================================================
# 6. 保存结果
# ============================================================

output_dir = "/mnt/f/LEM/output"

# 保存高程数据为 .npy 文件
npy_path = f"{output_dir}/final_elevation.npy"
np.save(npy_path, final_elevation)
print(f"高程数据已保存: {npy_path}")

# 保存可视化图片
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# 左图：最终高程图（俯视图）
im1 = axes[0].imshow(
    final_elevation,
    cmap="terrain",
    origin="lower",
    extent=[0, ncols * dx / 1000, 0, nrows * dx / 1000],
)
axes[0].set_title("Final Topography (Top View)", fontsize=13)
axes[0].set_xlabel("X (km)")
axes[0].set_ylabel("Y (km)")
plt.colorbar(im1, ax=axes[0], label="Elevation (m)", shrink=0.8)

# 右图：沿中间行的高程剖面
mid_row = nrows // 2
x_km = np.arange(ncols) * dx / 1000
axes[1].plot(x_km, final_elevation[mid_row, :], 'k-', linewidth=1.5)
axes[1].fill_between(x_km, 0, final_elevation[mid_row, :],
                     alpha=0.3, color="sienna")
axes[1].set_title(f"Elevation Profile (Row {mid_row})", fontsize=13)
axes[1].set_xlabel("X (km)")
axes[1].set_ylabel("Elevation (m)")
axes[1].set_ylim(bottom=0)
axes[1].grid(True, alpha=0.3)

plt.tight_layout()
png_path = f"{output_dir}/final_elevation.png"
plt.savefig(png_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"可视化图片已保存: {png_path}")

# 保存演化过程图
if elevation_history:
    n_snapshots = len(elevation_history)
    fig2, axes2 = plt.subplots(1, n_snapshots, figsize=(4 * n_snapshots, 4))
    if n_snapshots == 1:
        axes2 = [axes2]

    for idx, (ax, elev) in enumerate(zip(axes2, elevation_history)):
        elev_2d = elev.reshape((nrows, ncols))
        im = ax.imshow(
            elev_2d,
            cmap="terrain",
            origin="lower",
            extent=[0, ncols * dx / 1000, 0, nrows * dx / 1000],
        )
        time_kyr = (idx + 1) * record_interval * dt / 1000
        ax.set_title(f"t = {time_kyr:.0f} kyr", fontsize=11)
        ax.set_xlabel("X (km)")
        if idx == 0:
            ax.set_ylabel("Y (km)")
        plt.colorbar(im, ax=ax, shrink=0.7)

    plt.suptitle("Landscape Evolution Through Time", fontsize=14, y=1.02)
    plt.tight_layout()
    evolution_path = f"{output_dir}/elevation_evolution.png"
    plt.savefig(evolution_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"演化过程图已保存: {evolution_path}")

print()
print("=" * 60)
print("Demo 运行完毕！所有输出文件位于: /mnt/f/LEM/output/")
print("=" * 60)
