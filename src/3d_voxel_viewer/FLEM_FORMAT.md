# .flem 文件格式规范与构建指南

`.flem`（**F**astscape **L**andscape **E**volution **M**odel）是一种专为地貌演化模型与体素渲染管线设计的高性能紧凑型二进制地形交换格式。

本文档详细说明 `.flem` 文件的二进制存储结构、数学标量场语义、数据归一化规范，以及如何通过物理模拟、过程生成或现有 GIS 数据构建 `.flem` 文件。

---

## 1. 设计目标与背景

在传统地理信息系统（GIS）或地貌模拟输出中，数据通常以 NetCDF、GeoTIFF、HDF5 或 ASCII Grid 等格式存储。然而在实时体素图形渲染引擎（如基于 Raylib 的 `voxel_terrain_viewer`）中，上述格式存在以下问题：
1. **解析开销高**：复杂的元数据与分块压缩算法使得解析耗时过长，无法支持毫秒级流式读取；
2. **标量场分离**：地貌学可视化往往需要协同渲染**高程场（Elevation）**、**汇水面积（Drainage Area / Flow Accumulation）**及**侵蚀速率（Erosion Rate）**，多文件分离存储增加了管理复杂度；
3. **内存对齐不友好**：非对齐的格式无法直接执行一次性零拷贝或裸指针映射（Direct Memory Mapping / Read-to-Buffer）。

为此，`.flem` 格式被设计为：
- **严格 64 字节头部**：1 字节紧凑对齐，包含完整的网格几何与物理范围元数据；
- **全单精度浮点连续排布**：数据体由三个连续的连续行优先（Row-Major）`float32` 标量数组组成；
- **高效 IO 流**：文件加载仅需一次 `Header` 读取与三次顺序流式内存拷贝，支持加载 2048×2048（千万级体素）规模的大型地貌文件。

---

## 2. 文件二进制布局 (Binary Layout)

`.flem` 采用 **小端序（Little-Endian）** 存储，整体由两部分构成：

```
+-------------------------------------------------------------------------+
|                        FLEM Header (64 Bytes)                           |
+-------------------------------------------------------------------------+
|                  Elevation Array: nx * ny * sizeof(float)               |
+-------------------------------------------------------------------------+
|                Drainage Area Array: nx * ny * sizeof(float)             |
+-------------------------------------------------------------------------+
|                 Erosion Rate Array: nx * ny * sizeof(float)             |
+-------------------------------------------------------------------------+
```

### 2.1 文件总体大小计算

设横向网格列数为 $N_x$，纵向网格行数为 $N_y$，单个网格标量使用 IEEE 754 32 位浮点数（4 字节）。总数据点数 $N_{\text{total}} = N_x \times N_y$。

$$\text{Total File Size} = 64 + 3 \times (N_x \times N_y \times 4) \text{ Bytes}$$

| 分辨率 | 网格点总量 | 单个标量场大小 | 总文件大小 |
| :--- | :--- | :--- | :--- |
| **64 × 64** | 4,096 | 16 KB | **48.06 KB** |
| **512 × 512** | 262,144 | 1 MB | **3.00 MB** |
| **1024 × 1024** | 1,048,576 | 4 MB | **12.00 MB** |
| **2048 × 2048** | 4,194,304 | 16 MB | **48.00 MB** |

---

## 3. 文件头规范 (Header Specification)

Header 严格占用 **64 字节**。在 C/C++ 中需使用 `#pragma pack(push, 1)` 或 `__attribute__((packed))` 禁止结构体内存填充。

### 3.1 字段字节分布表

| 偏移 (Offset) | 字段名称 | 数据类型 | 字节大小 | 描述与单位 |
| :--- | :--- | :--- | :--- | :--- |
| `0x00 - 0x03` | `magic` | `char[4]` | 4 | 魔数固定为 ASCII 字符 `'F'`, `'L'`, `'E'`, `'M'` |
| `0x04 - 0x07` | `version` | `uint32_t` | 4 | 文件格式版本号（当前固定为 `1`） |
| `0x08 - 0x0B` | `nx` | `uint32_t` | 4 | 网格列数（X 方向网格点数） |
| `0x0C - 0x0F` | `ny` | `uint32_t` | 4 | 网格行数（Y 方向网格点数） |
| `0x10 - 0x13` | `length_x` | `float` | 4 | 真实物理跨度 X（米，如 20000.0） |
| `0x14 - 0x17` | `length_y` | `float` | 4 | 真实物理跨度 Y（米，如 20000.0） |
| `0x18 - 0x1B` | `h_min` | `float` | 4 | 地形最小高程（米） |
| `0x1C - 0x1F` | `h_max` | `float` | 4 | 地形最大高程（米） |
| `0x20 - 0x23` | `area_min` | `float` | 4 | 最小汇水/排水面积（$\text{m}^2$） |
| `0x24 - 0x27` | `area_max` | `float` | 4 | 最大汇水/排水面积（$\text{m}^2$） |
| `0x28 - 0x2B` | `erosion_min` | `float` | 4 | 地表最小侵蚀速率（$\text{m/yr}$ 或相对标量） |
| `0x2C - 0x2F` | `erosion_max` | `float` | 4 | 地表最大侵蚀速率（$\text{m/yr}$ 或相对标量） |
| `0x30 - 0x33` | `has_water` | `uint32_t` | 4 | 水面标志位（`1` 表示存在水体/海平面，`0` 表示无） |
| `0x34 - 0x37` | `water_level` | `float` | 4 | 水面/基准面海拔高度（米） |
| `0x38 - 0x3F` | `reserved` | `uint8_t[8]` | 8 | 保留对齐填充字段（全填 `0x00`，供未来扩展） |

### 3.2 C/C++ 结构体定义

```cpp
#include <cstdint>

#pragma pack(push, 1)
struct FLEMHeader {
    char magic[4];          // "FLEM" (0x4D454C46)
    uint32_t version;       // Version (currently 1)
    uint32_t nx;            // Grid columns (X dimension)
    uint32_t ny;            // Grid rows (Y/Z dimension)
    float length_x;         // Physical extent in X (m)
    float length_y;         // Physical extent in Y (m)
    float h_min;            // Elevation minimum (m)
    float h_max;            // Elevation maximum (m)
    float area_min;         // Drainage area minimum (m^2)
    float area_max;         // Drainage area maximum (m^2)
    float erosion_min;      // Erosion rate minimum
    float erosion_max;      // Erosion rate maximum
    uint32_t has_water;     // 1 if water level is defined
    float water_level;      // Water level threshold (m)
    uint8_t reserved[8];    // Reserved padding (all 0)
};
#pragma pack(pop)

static_assert(sizeof(FLEMHeader) == 64, "FLEMHeader must be exactly 64 bytes");
```

---

## 4. 数据体组织与标量语义 (Payload Semantics)

在 Header 之后，紧随三段大小均为 `nx * ny * 4` 字节的连续浮点数缓冲区：

### 4.1 标量场说明与网格排布

1. **高程场 `elevation` (`float32[nx * ny]`)**：
   - 记录地形的连续几何高度 $H(x, y)$。
   - 坐标映射：行优先顺序，即点 $(x, y)$ 的数组索引为：
     $$\text{index} = y \times n_x + x \quad (0 \le x < n_x, \; 0 \le y < n_y)$$
2. **汇水面积场 `drainage_area` (`float32[nx * ny]`)**：
   - 地貌水文学中的上游集水面积（Drainage / Catchment Area）$A(x, y)$，单位通常为 $\text{m}^2$。
   - 在水流汇聚点（如峡谷底部、干流河道），该值可达数百万甚至数千万；在山脊和分水岭处接近网格单体面积。
3. **侵蚀速率场 `erosion_rate` (`float32[nx * ny]`)**：
   - 瞬时侵蚀速率 $\dot{\epsilon}(x, y)$，反映河流切削与山坡重力崩塌的动力学强度。

### 4.2 标量归一化算法

体素渲染管线及 Shader 对不同标量场执行标准化（映射到 $[0.0, 1.0]$ 区间）：

1. **高程线性归一化**：
   $$\tilde{h}(x, y) = \text{clamp}\left(\frac{H(x, y) - h_{\min}}{h_{\max} - h_{\min}}, 0.0, 1.0\right)$$

2. **汇水面积对数归一化（Logarithmic Scaling）**：
   由于汇水面积跨越数个数量级（呈现幂律分布），必须使用对数缩放以揭示树枝状水系网络：
   $$\tilde{A}(x, y) = \text{clamp}\left(\frac{\log_{10}(1.0 + A(x, y)) - \log_{10}(1.0 + \max(0, \text{area}_{\min}))}{\log_{10}(1.0 + \max(1, \text{area}_{\max})) - \log_{10}(1.0 + \max(0, \text{area}_{\min}))}, 0.0, 1.0\right)$$

3. **侵蚀速率归一化**：
   $$\tilde{\epsilon}(x, y) = \text{clamp}\left(\frac{\dot{\epsilon}(x, y) - \text{erosion}_{\min}}{\text{erosion}_{\max} - \text{erosion}_{\min}}, 0.0, 1.0\right)$$

4. **体素离散化（RTN 舍入算法）**：
   体素化渲染器使用四舍五入到最近整数（Round-to-Nearest）将连续高程转换为离散体素列高：
   $$y_{\text{voxel}} = \text{round}\Big(\tilde{h}(x, y) \times (V_{\text{height}} - 1)\Big)$$

---

## 5. 如何构建与生成 .flem 文件

本工程提供了多种生成 `.flem` 文件的方法：

### 方法一：使用 Fastscape 物理演化模拟生成（推荐）

工程内置了 Python 仿真导出脚本 `scripts/export_fastscape.py`，基于 Fastscape 地貌动力学引擎求解河道切削（Stream Power Law）与地表扩散方程：

$$\frac{\partial h}{\partial t} = U - K_f A^m S^n + K_d \nabla^2 h$$

#### 1. 运行内置命令行工具

```bash
# 生成 64x64 基础丘陵地形
.venv/bin/python scripts/export_fastscape.py -o resources/sample_terrain.flem --nx 64 --ny 64 --preset sample

# 生成 64x64 险峻高山地形
.venv/bin/python scripts/export_fastscape.py -o resources/mountain_terrain.flem --nx 64 --ny 64 --preset mountain

# 生成 2048x2048 老年期深度侵蚀峡谷地貌（419 万网格点，超高地貌复杂度）
.venv/bin/python scripts/export_fastscape.py -o resources/terrain_2048_eroded.flem --nx 2048 --ny 2048 --preset eroded
```

#### 2. 内置预设参数特性

| 预设类型 (`--preset`) | 抬升率 $U$ | 扩散系数 $K_d$ | 河流侵蚀 $K_f$ | 模拟时长 $T$ | 地貌特征描述 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `sample` | $2 \times 10^{-3}$ | $5 \times 10^{-2}$ | $2 \times 10^{-5}$ | 100,000 | 典型平衡态丘陵与宽缓河网 |
| `mountain` | $4 \times 10^{-3}$ | $3 \times 10^{-2}$ | $3 \times 10^{-5}$ | 100,000 | 构造抬升强烈的陡峭高山 |
| `coastal` | $1 \times 10^{-3}$ | $8 \times 10^{-2}$ | $1.5 \times 10^{-5}$ | 100,000 | 平缓入海三角洲与低洼海岸线 |
| `eroded` | $1 \times 10^{-3}$ | $5 \times 10^{-2}$ | $2 \times 10^{-4}$ | 200,000 | 极度深切的幼老年期峡谷、密布树枝状水系 |

---

### 方法二：通过通用 Python 脚本导出自定义数组

如果你有已有的 DEM 高程矩阵（如从 GeoTIFF、PNG 高度图或 NumPy 数组获得），可通过以下独立 Python 函数打包导出为 `.flem`：

```python
import struct
import numpy as np

def save_to_flem(filepath, elevation, drainage_area=None, erosion_rate=None,
                 length_x=20000.0, length_y=20000.0, water_level=0.0):
    """
    将 2D NumPy 数组保存为 .flem 格式。
    
    参数:
        filepath: 目标 .flem 路径
        elevation: (ny, nx) float32 高程矩阵
        drainage_area: (ny, nx) float32 汇水面积（可选，默认全 0）
        erosion_rate: (ny, nx) float32 侵蚀速率（可选，默认全 0）
        length_x, length_y: 物理尺寸（米）
        water_level: 海平面高度（米）
    """
    ny, nx = elevation.shape
    elevation = elevation.astype(np.float32)
    
    if drainage_area is None:
        drainage_area = np.zeros_like(elevation, dtype=np.float32)
    else:
        drainage_area = drainage_area.astype(np.float32)
        
    if erosion_rate is None:
        erosion_rate = np.zeros_like(elevation, dtype=np.float32)
    else:
        erosion_rate = erosion_rate.astype(np.float32)

    h_min, h_max = float(elevation.min()), float(elevation.max())
    a_min, a_max = float(drainage_area.min()), float(drainage_area.max())
    e_min, e_max = float(erosion_rate.min()), float(erosion_rate.max())

    has_water = 1 if h_min <= water_level else 0
    magic = b'FLEM'
    version = 1
    reserved = b'\x00' * 8

    # 封包 64 字节头部: <4sIII8fIf8s
    header = struct.pack(
        '<4sIII8fIf8s',
        magic, version, nx, ny,
        float(length_x), float(length_y),
        h_min, h_max,
        a_min, a_max,
        e_min, e_max,
        has_water, float(water_level),
        reserved
    )
    assert len(header) == 64, f"Header size error: {len(header)}"

    with open(filepath, 'wb') as f:
        f.write(header)
        f.write(elevation.tobytes())
        f.write(drainage_area.tobytes())
        f.write(erosion_rate.tobytes())
        
    print(f"Successfully exported {filepath} ({nx}x{ny})")
```

---

### 方法三：在 C++ 中生成与写入

在 C++ 环境下，可直接通过流操作将结构体与连续内存写入二进制文件：

```cpp
#include <fstream>
#include <vector>
#include "core/fastscape_loader.h"

bool SaveFLEM(const std::string& filepath, const FastscapeData& data) {
    std::ofstream out(filepath, std::ios::binary);
    if (!out.is_open()) return false;

    // 1. 写入 64 字节 Header
    out.write(reinterpret_cast<const char*>(&data.header), sizeof(FLEMHeader));

    // 2. 依次写入三个标量场数组
    size_t count = data.header.nx * data.header.ny;
    out.write(reinterpret_cast<const char*>(data.elevation.data()), count * sizeof(float));
    out.write(reinterpret_cast<const char*>(data.drainage_area.data()), count * sizeof(float));
    out.write(reinterpret_cast<const char*>(data.erosion_rate.data()), count * sizeof(float));

    return out.good();
}
```

---

## 6. 读取与解析规范

### 6.1 C++ 读取实现示例

```cpp
bool FastscapeLoader::LoadFromFile(const std::string& filepath, FastscapeData& out_data) {
    std::ifstream file(filepath, std::ios::binary);
    if (!file.is_open()) return false;

    // 1. 读取并校验 Header
    file.read(reinterpret_cast<char*>(&out_data.header), sizeof(FLEMHeader));
    if (file.gcount() != sizeof(FLEMHeader)) return false;

    // 校验魔数
    if (std::string(out_data.header.magic, 4) != "FLEM") return false;
    // 校验版本号
    if (out_data.header.version != 1) return false;

    uint32_t total_points = out_data.header.nx * out_data.header.ny;
    if (total_points == 0 || total_points > 4096 * 4096) return false;

    // 2. 分配内存并直接连续读入
    out_data.elevation.resize(total_points);
    out_data.drainage_area.resize(total_points);
    out_data.erosion_rate.resize(total_points);

    file.read(reinterpret_cast<char*>(out_data.elevation.data()), total_points * sizeof(float));
    file.read(reinterpret_cast<char*>(out_data.drainage_area.data()), total_points * sizeof(float));
    file.read(reinterpret_cast<char*>(out_data.erosion_rate.data()), total_points * sizeof(float));

    out_data.is_valid = file.good();
    return out_data.is_valid;
}
```

### 6.2 Python 读取与质检

可使用 `scripts/visualize_terrain.py` 直接解析并生成二维渲染图：

```python
import struct
import numpy as np

def load_flem(filepath):
    with open(filepath, 'rb') as f:
        header = f.read(64)
        magic, ver, nx, ny, lx, ly, hmin, hmax, amin, amax, emin, emax, has_w, wlevel = \
            struct.unpack('<4sIII8fIf', header[:56])
        total = nx * ny
        elev = np.fromfile(f, dtype=np.float32, count=total).reshape((ny, nx))
        area = np.fromfile(f, dtype=np.float32, count=total).reshape((ny, nx))
        erosion = np.fromfile(f, dtype=np.float32, count=total).reshape((ny, nx))
    return elev, area, erosion, (nx, ny, lx, ly, hmin, hmax)
```

---

## 7. 验证与可视化工具

生成 `.flem` 文件后，可使用以下工具进行验证：

1. **2D 水文与阴影浮雕质检**：
   ```bash
   .venv/bin/python scripts/visualize_terrain.py
   # 输出为 resources/eroded_preview.png，展示大范围光照阴影地貌与树枝状切削水系。
   ```

2. **3D 实时交互体素查看器**：
   ```bash
   # 打开 3D 查看器浏览
   ./build/src/voxel_terrain_viewer resources/sample_terrain.flem

   # 支持直接在窗口中拖拽（Drag & Drop）任何 .flem 文件实时重载！
   ```

3. **完整自动化测试套件**：
   ```bash
   ./scripts/verify_all.sh
   ```
