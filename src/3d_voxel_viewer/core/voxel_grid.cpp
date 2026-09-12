#include "voxel_grid.h"
#include <cmath>
#include <algorithm>
#include <iostream>

void VoxelGrid::Allocate(int sx, int sy, int sz) {
    size_x = sx;
    size_y = sy;
    size_z = sz;
    voxels.assign(sx * sy * sz, VOXEL_AIR);
    column_attrs.assign(sx * sz, ColumnAttributes{});
}

void VoxelGrid::Clear() {
    std::fill(voxels.begin(), voxels.end(), VOXEL_AIR);
}

bool VoxelGrid::QuantizeFromFastscape(const FastscapeData& data,
                                     int vertical_voxels,
                                     int water_level_voxels) {
    if (!data.is_valid) {
        std::cerr << "[VoxelGrid] Cannot quantize from invalid Fastscape data" << std::endl;
        return false;
    }

    int sx = static_cast<int>(data.header.nx);
    int sz = static_cast<int>(data.header.ny);
    // Vertical headroom for water or peaks
    int sy = std::max(vertical_voxels + 4, water_level_voxels + 4);

    Allocate(sx, sy, sz);

    max_ground_y = 0;
    center_ground_y = 0.0f;

    // First pass: compute column heights with Round-to-Nearest (RTN)
    for (int z = 0; z < sz; ++z) {
        for (int x = 0; x < sx; ++x) {
            float norm_elev = data.GetNormalizedElevation(x, z);
            float norm_drain = data.GetNormalizedDrainage(x, z);
            float norm_eros = data.GetNormalizedErosion(x, z);

            // RTN Quantization: std::round maps continuous elevation to nearest integer voxel height
            int quantized_y = static_cast<int>(std::round(norm_elev * (vertical_voxels - 1)));
            quantized_y = std::clamp(quantized_y, 0, sy - 2);

            if (quantized_y > max_ground_y) {
                max_ground_y = quantized_y;
            }

            int col_idx = GetColumnIndex(x, z);
            column_attrs[col_idx].norm_elevation = norm_elev;
            column_attrs[col_idx].norm_drainage = norm_drain;
            column_attrs[col_idx].norm_erosion = norm_eros;
            column_attrs[col_idx].ground_height = quantized_y;
            column_attrs[col_idx].water_height = std::max(quantized_y, water_level_voxels);
        }
    }

    // Calculate center ground average height
    int r = std::max(2, std::min(sx, sz) / 16);
    int mid_x = sx / 2;
    int mid_z = sz / 2;
    double sum_y = 0.0;
    int count_center = 0;
    for (int cz = mid_z - r; cz <= mid_z + r; ++cz) {
        for (int cx = mid_x - r; cx <= mid_x + r; ++cx) {
            if (InBounds(cx, 0, cz)) {
                sum_y += column_attrs[GetColumnIndex(cx, cz)].ground_height;
                count_center++;
            }
        }
    }
    center_ground_y = (count_center > 0) ? static_cast<float>(sum_y / count_center) : 10.0f;

    // Second pass: fill voxel grid layers based on geological & morphological rules
    for (int z = 0; z < sz; ++z) {
        for (int x = 0; x < sx; ++x) {
            const ColumnAttributes& col = GetColumn(x, z);
            int gy = col.ground_height;

            // Compute local slope to distinguish cliffs/rock faces from flat grass
            int dz_left = (x > 0) ? std::abs(gy - GetColumn(x - 1, z).ground_height) : 0;
            int dz_right = (x < sx - 1) ? std::abs(gy - GetColumn(x + 1, z).ground_height) : 0;
            int dz_back = (z > 0) ? std::abs(gy - GetColumn(x, z - 1).ground_height) : 0;
            int dz_front = (z < sz - 1) ? std::abs(gy - GetColumn(x, z + 1).ground_height) : 0;
            int max_step = std::max({dz_left, dz_right, dz_back, dz_front});
            bool is_steep = (max_step >= 2);

            // Fill ground voxels from bottom y=0 to gy
            for (int y = 0; y <= gy; ++y) {
                if (y == 0) {
                    SetVoxel(x, y, z, VOXEL_BEDROCK);
                } else if (y < gy - 3) {
                    SetVoxel(x, y, z, VOXEL_STONE);
                } else if (y < gy) {
                    SetVoxel(x, y, z, VOXEL_DIRT);
                } else {
                    // Topmost surface voxel (y == gy)
                    if (gy <= water_level_voxels) {
                        SetVoxel(x, y, z, VOXEL_SAND); // Coast / riverbed beach
                    } else if (gy >= vertical_voxels * 0.88f) {
                        SetVoxel(x, y, z, VOXEL_SNOW); // High alpine snow
                    } else if (is_steep || gy >= vertical_voxels * 0.70f) {
                        SetVoxel(x, y, z, VOXEL_STONE); // Mountain rock cliff
                    } else {
                        SetVoxel(x, y, z, VOXEL_GRASS); // Fertile grass / vegetation
                    }
                }
            }

            // Fill water voxels if ground is below water level
            if (data.header.has_water && gy < water_level_voxels) {
                for (int y = gy + 1; y <= water_level_voxels; ++y) {
                    SetVoxel(x, y, z, VOXEL_WATER);
                }
            }
        }
    }

    std::cout << "[VoxelGrid] RTN Quantization completed: " << sx << "x" << sy << "x" << sz
              << " | Solid voxels: " << CountSolidVoxels()
              << " | Water voxels: " << CountWaterVoxels() << std::endl;
    return true;
}

int VoxelGrid::GetGroundHeightAt(int x, int z) const {
    if (x < 0 || x >= size_x || z < 0 || z >= size_z) return 0;
    return column_attrs[GetColumnIndex(x, z)].ground_height;
}

int VoxelGrid::CountSolidVoxels() const {
    int count = 0;
    for (uint8_t v : voxels) {
        if (v != VOXEL_AIR && v != VOXEL_WATER) {
            count++;
        }
    }
    return count;
}

int VoxelGrid::CountWaterVoxels() const {
    int count = 0;
    for (uint8_t v : voxels) {
        if (v == VOXEL_WATER) {
            count++;
        }
    }
    return count;
}
