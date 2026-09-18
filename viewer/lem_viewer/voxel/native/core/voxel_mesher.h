#pragma once

#include "raylib.h"
#include "voxel_grid.h"
#include "palette_manager.h"
#include "profiler.h"
#include <vector>
#include <cstddef>

struct MesherStats {
    uint64_t total_solid_voxels = 0;
    uint64_t unoptimized_faces = 0;
    uint64_t optimized_quads = 0;
    uint64_t terrain_triangles = 0;
    uint64_t water_triangles = 0;
    int draw_calls = 0;
    int submesh_count = 0;
    float reduction_percentage = 0.0f;
    float meshing_time_ms = 0.0f;
    size_t memory_ram_bytes = 0;
    size_t memory_vram_bytes = 0;
};

class VoxelMesher {
public:
    VoxelMesher() = default;
    ~VoxelMesher();

    Model terrain_model{};
    Model water_model{};
    bool has_terrain_model = false;
    bool has_water_model = false;

    std::vector<BoundingBox> terrain_submesh_bounds;
    std::vector<BoundingBox> water_submesh_bounds;

    MesherStats stats;

    static constexpr int CHUNK_SIZE = 128;
    static constexpr int MAX_QUADS_PER_SUBMESH = 15000; // 60,000 vertices < 65,535 (16-bit index limit)

    // Generates chunked greedy-meshed Raylib models supporting arbitrary grid sizes up to 2048+
    bool BuildMesh(const VoxelGrid& grid, const PaletteManager& palette);

    // Updates vertex colors across all submeshes without re-meshing geometry
    void UpdateColors(const VoxelGrid& grid, const PaletteManager& palette);

    // Renders the terrain and water models with frustum culling and backface optimization
    void Draw(Vector3 position, float scale = 1.0f,
              const Camera3D* camera = nullptr, float aspect = 1.777f,
              FrameProfile* profile = nullptr,
              float far_plane = 50000.0f);

    void Unload();

private:
    struct QuadData {
        Vector3 v0, v1, v2, v3;
        Vector3 normal;
        uint8_t voxel_type;
        int col_x, col_z;
        int normal_axis;
        int normal_sign;
        int ao[4];
        bool is_water;
    };

    std::vector<QuadData> terrain_quads;
    std::vector<QuadData> water_quads;

    Mesh BuildSubmesh(const QuadData* quads,
                      int num_quads,
                      const VoxelGrid& grid,
                      const PaletteManager& palette,
                      BoundingBox& out_bounds);

    Model CreateModelFromMeshes(const std::vector<Mesh>& meshes);

    int CalculateVertexAO(const VoxelGrid& grid,
                          int x, int y, int z,
                          int axis, int sign,
                          int corner_u, int corner_v) const;

    void MeshChunk(const VoxelGrid& grid, const PaletteManager& palette,
                   int x0, int x1,
                   int z0, int z1,
                   std::vector<QuadData>& out_terrain,
                   std::vector<QuadData>& out_water) const;
};
