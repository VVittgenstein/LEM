#pragma once

#include "fastscape_loader.h"
#include <vector>
#include <cstdint>
#include <cstddef>

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
    uint32_t display_color = 0xff808080;
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

    // q+1 (voxel top) maps to h_min+q*height_step. All axes use scene_unit_m.
    bool physical_coordinates = false;
    double scene_unit_m = 1.0;
    float cell_x = 1, cell_z = 1, height_step = 1, height_origin = -1;
    float water_surface = 0;
    float floor_height = 0;
    int water_layer = -1;
    void ConfigurePhysical(const FastscapeData& data, double dx, double dy,
                           int levels, double exaggeration);
    float WorldHeight(float y, bool water = false) const;
    float GroundHeightWorldAt(float x, float z) const;

    std::vector<uint8_t> voxels; // Size: size_x * size_y * size_z
    std::vector<ColumnAttributes> column_attrs; // Size: size_x * size_z

    void Allocate(int sx, int sy, int sz);
    static size_t CheckedVoxelCount(int sx, int sy, int sz);
    void Clear();

    // Fast inline accessors
    inline size_t GetIndex(int x, int y, int z) const {
        return (size_t(y) * size_t(size_z) + size_t(z)) * size_t(size_x) + size_t(x);
    }

    inline size_t GetColumnIndex(int x, int z) const {
        return size_t(z) * size_t(size_x) + size_t(x);
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

    uint64_t CountSolidVoxels() const;
    uint64_t CountWaterVoxels() const;
};
