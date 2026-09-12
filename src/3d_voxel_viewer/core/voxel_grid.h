#pragma once

#include "fastscape_loader.h"
#include <vector>
#include <cstdint>

enum VoxelType : uint8_t {
    VOXEL_AIR = 0,
    VOXEL_BEDROCK = 1,
    VOXEL_STONE = 2,
    VOXEL_DIRT = 3,
    VOXEL_GRASS = 4,
    VOXEL_SNOW = 5,
    VOXEL_SAND = 6,
    VOXEL_WATER = 7,
    VOXEL_COUNT
};

struct ColumnAttributes {
    float norm_elevation = 0.0f;
    float norm_drainage = 0.0f;
    float norm_erosion = 0.0f;
    int ground_height = 0;
    int water_height = 0;
};

class VoxelGrid {
public:
    VoxelGrid() = default;
    ~VoxelGrid() = default;

    // Dimensions: X = width, Y = vertical height, Z = depth
    int size_x = 0;
    int size_y = 0;
    int size_z = 0;

    std::vector<uint8_t> voxels; // Size: size_x * size_y * size_z
    std::vector<ColumnAttributes> column_attrs; // Size: size_x * size_z

    void Allocate(int sx, int sy, int sz);
    void Clear();

    // Fast inline accessors
    inline int GetIndex(int x, int y, int z) const {
        return (y * size_z + z) * size_x + x;
    }

    inline int GetColumnIndex(int x, int z) const {
        return z * size_x + x;
    }

    inline bool InBounds(int x, int y, int z) const {
        return x >= 0 && x < size_x && y >= 0 && y < size_y && z >= 0 && z < size_z;
    }

    inline uint8_t GetVoxel(int x, int y, int z) const {
        if (!InBounds(x, y, z)) return VOXEL_AIR;
        return voxels[GetIndex(x, y, z)];
    }

    inline void SetVoxel(int x, int y, int z, uint8_t type) {
        if (InBounds(x, y, z)) {
            voxels[GetIndex(x, y, z)] = type;
        }
    }

    inline const ColumnAttributes& GetColumn(int x, int z) const {
        return column_attrs[GetColumnIndex(x, z)];
    }

    inline bool IsSolid(int x, int y, int z) const {
        uint8_t v = GetVoxel(x, y, z);
        return v != VOXEL_AIR && v != VOXEL_WATER;
    }

    inline bool IsTransparent(int x, int y, int z) const {
        uint8_t v = GetVoxel(x, y, z);
        return v == VOXEL_AIR || v == VOXEL_WATER;
    }

    // RTN (Round-to-Nearest) Quantization from Fastscape terrain
    bool QuantizeFromFastscape(const FastscapeData& data,
                               int vertical_voxels = 36,
                               int water_level_voxels = 2);

    // Diagnostics & Terrain Metrics
    int max_ground_y = 0;
    float center_ground_y = 0.0f;

    int GetMaxGroundHeight() const { return max_ground_y; }
    float GetCenterGroundHeight() const { return center_ground_y; }
    int GetGroundHeightAt(int x, int z) const;

    int CountSolidVoxels() const;
    int CountWaterVoxels() const;
};
