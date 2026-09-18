#include "voxel_mesher.h"
#include "raymath.h"
#include "rlgl.h"
#include <iostream>
#include <algorithm>
#include <cstring>
#include <cmath>
#include <chrono>
#include <atomic>
#include <exception>

#if defined(_OPENMP)
#include <omp.h>
#endif

// 6-Plane Frustum structure for fast submesh frustum culling
struct FrustumPlane {
    float a, b, c, d;
    inline void Normalize() {
        float len = std::sqrt(a * a + b * b + c * c);
        if (len > 0.00001f) {
            float inv = 1.0f / len;
            a *= inv; b *= inv; c *= inv; d *= inv;
        }
    }
    inline float Distance(Vector3 p) const {
        return a * p.x + b * p.y + c * p.z + d;
    }
};

struct ViewFrustum {
    FrustumPlane planes[6];

    static ViewFrustum Extract(const Camera3D& camera, float aspect, float far_plane = 50000.0f) {
        Matrix matView = MatrixLookAt(camera.position, camera.target, camera.up);
        Matrix matProj = MatrixPerspective(camera.fovy * DEG2RAD, aspect, 0.001f, far_plane);
        Matrix vp = MatrixMultiply(matView, matProj);

        ViewFrustum f;
        // Left
        f.planes[0] = { vp.m3 + vp.m0, vp.m7 + vp.m4, vp.m11 + vp.m8, vp.m15 + vp.m12 };
        // Right
        f.planes[1] = { vp.m3 - vp.m0, vp.m7 - vp.m4, vp.m11 - vp.m8, vp.m15 - vp.m12 };
        // Bottom
        f.planes[2] = { vp.m3 + vp.m1, vp.m7 + vp.m5, vp.m11 + vp.m9, vp.m15 + vp.m13 };
        // Top
        f.planes[3] = { vp.m3 - vp.m1, vp.m7 - vp.m5, vp.m11 - vp.m9, vp.m15 - vp.m13 };
        // Near
        f.planes[4] = { vp.m3 + vp.m2, vp.m7 + vp.m6, vp.m11 + vp.m10, vp.m15 + vp.m14 };
        // Far
        f.planes[5] = { vp.m3 - vp.m2, vp.m7 - vp.m6, vp.m11 - vp.m10, vp.m15 - vp.m14 };

        for (int i = 0; i < 6; ++i) f.planes[i].Normalize();
        return f;
    }

    inline bool ContainsBox(const BoundingBox& box) const {
        for (int i = 0; i < 6; ++i) {
            Vector3 p{
                (planes[i].a > 0) ? box.max.x : box.min.x,
                (planes[i].b > 0) ? box.max.y : box.min.y,
                (planes[i].c > 0) ? box.max.z : box.min.z
            };
            if (planes[i].Distance(p) < 0.0f) {
                return false;
            }
        }
        return true;
    }
};

VoxelMesher::~VoxelMesher() {
    Unload();
}

void VoxelMesher::Unload() {
    if (has_terrain_model) {
        UnloadModel(terrain_model);
        has_terrain_model = false;
    }
    if (has_water_model) {
        UnloadModel(water_model);
        has_water_model = false;
    }
    terrain_quads.clear();
    water_quads.clear();
    terrain_submesh_bounds.clear();
    water_submesh_bounds.clear();
}

int VoxelMesher::CalculateVertexAO(const VoxelGrid& grid,
                                   int x, int y, int z,
                                   int axis, int sign,
                                   int corner_u, int corner_v) const {
    int du[3] = {0, 0, 0};
    int dv[3] = {0, 0, 0};
    int dn[3] = {0, 0, 0};
    dn[axis] = sign;

    int u_axis = (axis == 0) ? 1 : ((axis == 1) ? 2 : 0);
    int v_axis = (axis == 0) ? 2 : ((axis == 1) ? 0 : 1);

    du[u_axis] = (corner_u == 1) ? 1 : -1;
    dv[v_axis] = (corner_v == 1) ? 1 : -1;

    int ox = x + dn[0];
    int oy = y + dn[1];
    int oz = z + dn[2];

    bool s1 = grid.IsSolid(ox + du[0], oy + du[1], oz + du[2]);
    bool s2 = grid.IsSolid(ox + dv[0], oy + dv[1], oz + dv[2]);
    bool c  = grid.IsSolid(ox + du[0] + dv[0], oy + du[1] + dv[1], oz + du[2] + dv[2]);

    if (s1 && s2) {
        return 0; // Fully occluded concave corner
    }
    return 3 - ((s1 ? 1 : 0) + (s2 ? 1 : 0) + (c ? 1 : 0));
}

void VoxelMesher::MeshChunk(const VoxelGrid& grid, const PaletteManager& palette,
                            int x0, int x1,
                            int z0, int z1,
                            std::vector<QuadData>& out_terrain,
                            std::vector<QuadData>& out_water) const {
    int sy = grid.size_y;
    int cx_len = x1 - x0;
    int cz_len = z1 - z0;

    for (int d = 0; d < 3; ++d) {
        int U = 0, V = 0, D = 0;
        if (d == 0) { // X axis
            D = cx_len; U = sy; V = cz_len;
        } else if (d == 1) { // Y axis
            D = sy; U = cz_len; V = cx_len;
        } else { // Z axis
            D = cz_len; U = cx_len; V = sy;
        }

        Vector3 normal_base{
            (d == 0) ? 1.0f : 0.0f,
            (d == 1) ? 1.0f : 0.0f,
            (d == 2) ? 1.0f : 0.0f
        };

        struct MaskCell {
            bool visible = false;
            uint8_t type = 0;
            int col_x = 0;
            int col_z = 0;
            int voxel_x = 0, voxel_y = 0, voxel_z = 0;
            bool is_water = false;
            uint32_t color = 0;
            int ao[4] = {3,3,3,3};
            bool uniform_ao = true;
        };

        std::vector<MaskCell> mask(U * V);

        for (int sign = -1; sign <= 1; sign += 2) {
            Vector3 normal_vec = Vector3Scale(normal_base, static_cast<float>(sign));

            for (int slice = 0; slice < D; ++slice) {
                // Populate 2D mask
                for (int iv = 0; iv < V; ++iv) {
                    for (int iu = 0; iu < U; ++iu) {
                        int vx = 0, vy = 0, vz = 0;
                        if (d == 0) {
                            vx = x0 + slice; vy = iu; vz = z0 + iv;
                        } else if (d == 1) {
                            vx = x0 + iv; vy = slice; vz = z0 + iu;
                        } else {
                            vx = x0 + iu; vy = iv; vz = z0 + slice;
                        }

                        uint8_t current_type = grid.GetVoxel(vx, vy, vz);
                        if (current_type == VOXEL_AIR) continue;

                        int nx = vx + ((d == 0) ? sign : 0);
                        int ny = vy + ((d == 1) ? sign : 0);
                        int nz = vz + ((d == 2) ? sign : 0);

                        uint8_t neighbor_type = grid.GetVoxel(nx, ny, nz);

                        bool is_visible = false;
                        if (current_type == VOXEL_WATER) {
                            is_visible = (neighbor_type == VOXEL_AIR);
                        } else {
                            is_visible = (neighbor_type == VOXEL_AIR || neighbor_type == VOXEL_WATER);
                        }

                        if (is_visible) {
                            MaskCell& cell = mask[iv * U + iu];
                            cell.visible = true;
                            cell.type = current_type;
                            cell.col_x = vx;
                            cell.col_z = vz;
                            cell.voxel_x = vx;
                            cell.voxel_y = vy;
                            cell.voxel_z = vz;
                            cell.is_water = (current_type == VOXEL_WATER);
                            auto color=palette.GetFaceColor(current_type,grid.GetColumn(vx,vz),d,sign,3);
                            cell.color=uint32_t(color.r)|(uint32_t(color.g)<<8)|(uint32_t(color.b)<<16)|(uint32_t(color.a)<<24);
                            if(!cell.is_water) {
                                cell.ao[0]=CalculateVertexAO(grid,vx,vy,vz,d,sign,0,0);
                                cell.ao[1]=CalculateVertexAO(grid,vx,vy,vz,d,sign,1,0);
                                cell.ao[2]=CalculateVertexAO(grid,vx,vy,vz,d,sign,1,1);
                                cell.ao[3]=CalculateVertexAO(grid,vx,vy,vz,d,sign,0,1);
                            } else for(auto& a:cell.ao) a=3;
                            cell.uniform_ao=cell.ao[0]==cell.ao[1]&&cell.ao[0]==cell.ao[2]&&cell.ao[0]==cell.ao[3];
                        }
                    }
                }

                // Greedy meshing on mask
                for (int iv = 0; iv < V; ++iv) {
                    for (int iu = 0; iu < U;) {
                        const MaskCell& start = mask[iv * U + iu];
                        if (!start.visible) {
                            iu++;
                            continue;
                        }

                        int width = 1;
                        while (iu + width < U) {
                            const MaskCell& next_u = mask[iv * U + (iu + width)];
                            if (!next_u.visible || next_u.type != start.type || next_u.is_water != start.is_water ||
                                next_u.color!=start.color || !start.uniform_ao || !next_u.uniform_ao || next_u.ao[0]!=start.ao[0]) {
                                break;
                            }
                            width++;
                        }

                        int height = 1;
                        bool can_expand_v = true;
                        while (iv + height < V && can_expand_v) {
                            for (int k = 0; k < width; ++k) {
                                const MaskCell& next_v = mask[(iv + height) * U + (iu + k)];
                                if (!next_v.visible || next_v.type != start.type || next_v.is_water != start.is_water ||
                                    next_v.color!=start.color || !start.uniform_ao || !next_v.uniform_ao || next_v.ao[0]!=start.ao[0]) {
                                    can_expand_v = false;
                                    break;
                                }
                            }
                            if (can_expand_v) {
                                height++;
                            }
                        }

                        QuadData quad{};
                        quad.voxel_type = start.type;
                        quad.col_x = start.col_x;
                        quad.col_z = start.col_z;
                        quad.normal = normal_vec;
                        quad.normal_axis = d;
                        quad.normal_sign = sign;
                        quad.is_water = start.is_water;

                        float p_slice = 0.0f;
                        float u0 = 0.0f, u1 = 0.0f, v0 = 0.0f, v1 = 0.0f;

                        if (d == 0) {
                            p_slice = (sign > 0) ? static_cast<float>(x0 + slice + 1) : static_cast<float>(x0 + slice);
                            u0 = static_cast<float>(iu);
                            u1 = static_cast<float>(iu + width);
                            v0 = static_cast<float>(z0 + iv);
                            v1 = static_cast<float>(z0 + iv + height);
                        } else if (d == 1) {
                            p_slice = (sign > 0) ? static_cast<float>(slice + 1) : static_cast<float>(slice);
                            u0 = static_cast<float>(z0 + iu);
                            u1 = static_cast<float>(z0 + iu + width);
                            v0 = static_cast<float>(x0 + iv);
                            v1 = static_cast<float>(x0 + iv + height);
                        } else {
                            p_slice = (sign > 0) ? static_cast<float>(z0 + slice + 1) : static_cast<float>(z0 + slice);
                            u0 = static_cast<float>(x0 + iu);
                            u1 = static_cast<float>(x0 + iu + width);
                            v0 = static_cast<float>(iv);
                            v1 = static_cast<float>(iv + height);
                        }

                        auto MakeVertex = [&](float su, float sv) -> Vector3 {
                            Vector3 pos{0, 0, 0};
                            if (d == 0)      { pos.x = p_slice; pos.y = su;      pos.z = sv; }
                            else if (d == 1) { pos.x = sv;      pos.y = p_slice; pos.z = su; }
                            else             { pos.x = su;      pos.y = sv;      pos.z = p_slice; }
                            if(grid.physical_coordinates) {
                                pos.x=(pos.x-0.5f)*grid.cell_x;
                                pos.z=(pos.z-0.5f)*grid.cell_z;
                                pos.y=grid.WorldHeight(pos.y,quad.is_water);
                            }
                            return pos;
                        };

                        if (sign > 0) {
                            quad.v0 = MakeVertex(u0, v0);
                            quad.v1 = MakeVertex(u1, v0);
                            quad.v2 = MakeVertex(u1, v1);
                            quad.v3 = MakeVertex(u0, v1);
                        } else {
                            quad.v0 = MakeVertex(u0, v0);
                            quad.v1 = MakeVertex(u0, v1);
                            quad.v2 = MakeVertex(u1, v1);
                            quad.v3 = MakeVertex(u1, v0);
                        }

                        for(int a=0;a<4;++a) quad.ao[a]=start.ao[a];
                        if(sign<0) std::swap(quad.ao[1],quad.ao[3]);

                        if (quad.is_water) {
                            out_water.push_back(quad);
                        } else {
                            out_terrain.push_back(quad);
                        }

                        for (int hv = 0; hv < height; ++hv) {
                            for (int wu = 0; wu < width; ++wu) {
                                mask[(iv + hv) * U + (iu + wu)].visible = false;
                            }
                        }

                        iu += width;
                    }
                }
            }
        }
    }
}

bool VoxelMesher::BuildMesh(const VoxelGrid& grid, const PaletteManager& palette) {
    auto t_start = std::chrono::high_resolution_clock::now();
    Unload();

    int sx = grid.size_x;
    int sy = grid.size_y;
    int sz = grid.size_z;

    stats.total_solid_voxels = grid.CountSolidVoxels();
    stats.unoptimized_faces = stats.total_solid_voxels * 6;

    int num_chunks_x = (sx + CHUNK_SIZE - 1) / CHUNK_SIZE;
    int num_chunks_z = (sz + CHUNK_SIZE - 1) / CHUNK_SIZE;
    int total_chunks = num_chunks_x * num_chunks_z;

    std::vector<std::vector<QuadData>> chunk_terrain(total_chunks);
    std::vector<std::vector<QuadData>> chunk_water(total_chunks);
    std::vector<std::exception_ptr> chunk_errors(total_chunks);
    std::atomic<bool> cancelled{false};

    #pragma omp parallel for schedule(dynamic)
    for (int c = 0; c < total_chunks; ++c) {
        if(cancelled.load())continue;
        int cx = c % num_chunks_x;
        int cz = c / num_chunks_x;
        int x0 = cx * CHUNK_SIZE;
        int x1 = std::min(x0 + CHUNK_SIZE, sx);
        int z0 = cz * CHUNK_SIZE;
        int z1 = std::min(z0 + CHUNK_SIZE, sz);

        try{MeshChunk(grid, palette, x0, x1, z0, z1, chunk_terrain[c], chunk_water[c]);}
        catch(...){chunk_errors[c]=std::current_exception();cancelled.store(true);}
    }
    for(const auto& error:chunk_errors)if(error)std::rethrow_exception(error);

    // Consolidate quads
    size_t total_t = 0, total_w = 0;
    for (int c = 0; c < total_chunks; ++c) {
        total_t += chunk_terrain[c].size();
        total_w += chunk_water[c].size();
    }
    terrain_quads.reserve(total_t);
    water_quads.reserve(total_w);

    for (int c = 0; c < total_chunks; ++c) {
        terrain_quads.insert(terrain_quads.end(), chunk_terrain[c].begin(), chunk_terrain[c].end());
        water_quads.insert(water_quads.end(), chunk_water[c].begin(), chunk_water[c].end());
    }

    stats.optimized_quads = terrain_quads.size() + water_quads.size();
    stats.terrain_triangles = terrain_quads.size() * 2;
    stats.water_triangles = water_quads.size() * 2;

    if (stats.unoptimized_faces > 0) {
        stats.reduction_percentage = 100.0f * (1.0f - static_cast<float>(stats.optimized_quads) / stats.unoptimized_faces);
    }

    // Partition terrain quads into submeshes (<= MAX_QUADS_PER_SUBMESH)
    std::vector<Mesh> terrain_meshes;
    size_t total_t_quads = terrain_quads.size();
    for (size_t i = 0; i < total_t_quads; i += MAX_QUADS_PER_SUBMESH) {
        int count = int(std::min(size_t(MAX_QUADS_PER_SUBMESH), total_t_quads - i));
        BoundingBox bb{};
        terrain_meshes.push_back(BuildSubmesh(terrain_quads.data() + i, count, grid, palette, bb));
        terrain_submesh_bounds.push_back(bb);
    }
    if (!terrain_meshes.empty()) {
        terrain_model = CreateModelFromMeshes(terrain_meshes);
        has_terrain_model = true;
    }

    // Partition water quads into submeshes
    std::vector<Mesh> water_meshes;
    size_t total_w_quads = water_quads.size();
    for (size_t i = 0; i < total_w_quads; i += MAX_QUADS_PER_SUBMESH) {
        int count = int(std::min(size_t(MAX_QUADS_PER_SUBMESH), total_w_quads - i));
        BoundingBox bb{};
        water_meshes.push_back(BuildSubmesh(water_quads.data() + i, count, grid, palette, bb));
        water_submesh_bounds.push_back(bb);
    }
    if (!water_meshes.empty()) {
        water_model = CreateModelFromMeshes(water_meshes);
        has_water_model = true;
    }

    stats.submesh_count = static_cast<int>(terrain_meshes.size() + water_meshes.size());
    stats.draw_calls = stats.submesh_count;

    auto t_end = std::chrono::high_resolution_clock::now();
    stats.meshing_time_ms = std::chrono::duration<float, std::milli>(t_end - t_start).count();

    size_t vert_bytes = stats.optimized_quads * 4 * (sizeof(float) * 6 + sizeof(char) * 4);
    size_t idx_bytes = stats.optimized_quads * 6 * sizeof(unsigned short);
    stats.memory_vram_bytes = vert_bytes + idx_bytes;
    stats.memory_ram_bytes = sizeof(VoxelGrid) + (grid.voxels.size() * sizeof(uint8_t)) +
                             (grid.column_attrs.size() * sizeof(ColumnAttributes)) + stats.memory_vram_bytes;

    std::cout << "[VoxelMesher] Meshing complete: " << std::endl
              << "  Total Chunks:           " << total_chunks << " (" << num_chunks_x << "x" << num_chunks_z << ")" << std::endl
              << "  Meshing Time:           " << stats.meshing_time_ms << " ms" << std::endl
              << "  Unoptimized faces:      " << stats.unoptimized_faces << std::endl
              << "  Optimized quads:        " << stats.optimized_quads << std::endl
              << "  Face Reduction:         " << stats.reduction_percentage << "%" << std::endl
              << "  Triangles:              " << stats.terrain_triangles + stats.water_triangles << std::endl
              << "  Submeshes / Draw Calls: " << stats.draw_calls << std::endl
              << "  Estimated VRAM:         " << (stats.memory_vram_bytes / (1024.0f * 1024.0f)) << " MB" << std::endl;

    return has_terrain_model;
}

Mesh VoxelMesher::BuildSubmesh(const QuadData* quads,
                               int num_quads,
                               const VoxelGrid& grid,
                               const PaletteManager& palette,
                               BoundingBox& out_bounds) {
    Mesh mesh{};
    mesh.vertexCount = num_quads * 4;
    mesh.triangleCount = num_quads * 2;

    mesh.vertices  = static_cast<float*>(MemAlloc(mesh.vertexCount * 3 * sizeof(float)));
    mesh.normals   = static_cast<float*>(MemAlloc(mesh.vertexCount * 3 * sizeof(float)));
    mesh.colors    = static_cast<unsigned char*>(MemAlloc(mesh.vertexCount * 4 * sizeof(unsigned char)));
    mesh.indices   = static_cast<unsigned short*>(MemAlloc(mesh.triangleCount * 3 * sizeof(unsigned short)));

    out_bounds.min = Vector3{1e9f, 1e9f, 1e9f};
    out_bounds.max = Vector3{-1e9f, -1e9f, -1e9f};

    for (int i = 0; i < num_quads; ++i) {
        const QuadData& q = quads[i];
        int v_offset = i * 4;
        int t_offset = i * 6;

        const Vector3 quad_verts[4] = {q.v0, q.v1, q.v2, q.v3};
        const ColumnAttributes& col = grid.GetColumn(q.col_x, q.col_z);

        for (int k = 0; k < 4; ++k) {
            int vi = v_offset + k;
            mesh.vertices[vi * 3 + 0] = quad_verts[k].x;
            mesh.vertices[vi * 3 + 1] = quad_verts[k].y;
            mesh.vertices[vi * 3 + 2] = quad_verts[k].z;

            // Expand bounding box
            out_bounds.min.x = std::min(out_bounds.min.x, quad_verts[k].x);
            out_bounds.min.y = std::min(out_bounds.min.y, quad_verts[k].y);
            out_bounds.min.z = std::min(out_bounds.min.z, quad_verts[k].z);
            out_bounds.max.x = std::max(out_bounds.max.x, quad_verts[k].x);
            out_bounds.max.y = std::max(out_bounds.max.y, quad_verts[k].y);
            out_bounds.max.z = std::max(out_bounds.max.z, quad_verts[k].z);

            mesh.normals[vi * 3 + 0] = q.normal.x;
            mesh.normals[vi * 3 + 1] = q.normal.y;
            mesh.normals[vi * 3 + 2] = q.normal.z;

            Color c = palette.GetFaceColor(q.voxel_type, col, q.normal_axis, q.normal_sign, q.ao[k]);
            mesh.colors[vi * 4 + 0] = c.r;
            mesh.colors[vi * 4 + 1] = c.g;
            mesh.colors[vi * 4 + 2] = c.b;
            mesh.colors[vi * 4 + 3] = c.a;
        }

        // Anisotropic AO triangulation flip
        if (q.ao[0] + q.ao[2] < q.ao[1] + q.ao[3]) {
            mesh.indices[t_offset + 0] = v_offset + 1;
            mesh.indices[t_offset + 1] = v_offset + 2;
            mesh.indices[t_offset + 2] = v_offset + 3;

            mesh.indices[t_offset + 3] = v_offset + 1;
            mesh.indices[t_offset + 4] = v_offset + 3;
            mesh.indices[t_offset + 5] = v_offset + 0;
        } else {
            mesh.indices[t_offset + 0] = v_offset + 0;
            mesh.indices[t_offset + 1] = v_offset + 1;
            mesh.indices[t_offset + 2] = v_offset + 2;

            mesh.indices[t_offset + 3] = v_offset + 0;
            mesh.indices[t_offset + 4] = v_offset + 2;
            mesh.indices[t_offset + 5] = v_offset + 3;
        }
    }

    UploadMesh(&mesh, false);
    return mesh;
}

Model VoxelMesher::CreateModelFromMeshes(const std::vector<Mesh>& meshes) {
    Model model = { 0 };
    model.transform = MatrixIdentity();
    model.meshCount = static_cast<int>(meshes.size());
    model.meshes = static_cast<Mesh*>(MemAlloc(model.meshCount * sizeof(Mesh)));
    for (int i = 0; i < model.meshCount; ++i) {
        model.meshes[i] = meshes[i];
    }
    model.materialCount = 1;
    model.materials = static_cast<Material*>(MemAlloc(sizeof(Material)));
    model.materials[0] = LoadMaterialDefault();
    model.meshMaterial = static_cast<int*>(MemAlloc(model.meshCount * sizeof(int)));
    for (int i = 0; i < model.meshCount; ++i) {
        model.meshMaterial[i] = 0;
    }
    return model;
}

void VoxelMesher::UpdateColors(const VoxelGrid& grid, const PaletteManager& palette) {
    if (has_terrain_model && terrain_model.meshCount > 0) {
        size_t total_t_quads = terrain_quads.size();

        for (int m_idx = 0; m_idx < terrain_model.meshCount; ++m_idx) {
            Mesh& m = terrain_model.meshes[m_idx];
            size_t start_quad = size_t(m_idx) * MAX_QUADS_PER_SUBMESH;
            int num_quads = int(std::min(size_t(MAX_QUADS_PER_SUBMESH), total_t_quads - start_quad));

            #pragma omp parallel for schedule(static)
            for (int i = 0; i < num_quads; ++i) {
                const QuadData& q = terrain_quads[start_quad + i];
                const ColumnAttributes& col = grid.GetColumn(q.col_x, q.col_z);
                int v_offset = i * 4;

                for (int k = 0; k < 4; ++k) {
                    int vi = v_offset + k;
                    Color c = palette.GetFaceColor(q.voxel_type, col, q.normal_axis, q.normal_sign, q.ao[k]);
                    m.colors[vi * 4 + 0] = c.r;
                    m.colors[vi * 4 + 1] = c.g;
                    m.colors[vi * 4 + 2] = c.b;
                    m.colors[vi * 4 + 3] = c.a;
                }
            }
            UpdateMeshBuffer(m, 3, m.colors, m.vertexCount * 4 * sizeof(unsigned char), 0);
        }
    }
}

void VoxelMesher::Draw(Vector3 position, float scale, const Camera3D* camera, float aspect, FrameProfile* profile, float far_plane) {
    if (!has_terrain_model && !has_water_model) return;

    // Enable hardware backface culling to eliminate redundant backface rasterization
    rlEnableBackfaceCulling();

    bool do_frustum = (camera != nullptr && profile != nullptr && profile->frustum_culling_enabled);
    ViewFrustum frustum;
    float total_aabb_test_us = 0.0f;

    if (do_frustum) {
        auto t_ext_start = std::chrono::high_resolution_clock::now();
        frustum = ViewFrustum::Extract(*camera, aspect, far_plane);
        auto t_ext_end = std::chrono::high_resolution_clock::now();
        profile->t_frustum_extract_us = std::chrono::duration<float, std::micro>(t_ext_end - t_ext_start).count();
    } else if (profile) {
        profile->t_frustum_extract_us = 0.0f;
    }

    Matrix matModel = MatrixMultiply(MatrixScale(scale, scale, scale), MatrixTranslate(position.x, position.y, position.z));

    if (has_terrain_model) {
        Material& mat = terrain_model.materials[0];
        for (int i = 0; i < terrain_model.meshCount; ++i) {
            bool visible = true;
            if (do_frustum && i < static_cast<int>(terrain_submesh_bounds.size())) {
                auto t_box_start = std::chrono::high_resolution_clock::now();
                visible = frustum.ContainsBox(terrain_submesh_bounds[i]);
                auto t_box_end = std::chrono::high_resolution_clock::now();
                total_aabb_test_us += std::chrono::duration<float, std::micro>(t_box_end - t_box_start).count();
            }
            if (visible) {
                DrawMesh(terrain_model.meshes[i], mat, matModel);
                if (profile) profile->visible_submeshes++;
            } else {
                if (profile) profile->culled_submeshes++;
            }
        }
    }

    if (has_water_model) {
        Material& mat = water_model.materials[0];
        for (int i = 0; i < water_model.meshCount; ++i) {
            bool visible = true;
            if (do_frustum && i < static_cast<int>(water_submesh_bounds.size())) {
                auto t_box_start = std::chrono::high_resolution_clock::now();
                visible = frustum.ContainsBox(water_submesh_bounds[i]);
                auto t_box_end = std::chrono::high_resolution_clock::now();
                total_aabb_test_us += std::chrono::duration<float, std::micro>(t_box_end - t_box_start).count();
            }
            if (visible) {
                DrawMesh(water_model.meshes[i], mat, matModel);
                if (profile) profile->visible_submeshes++;
            } else {
                if (profile) profile->culled_submeshes++;
            }
        }
    }

    if (profile) {
        profile->t_aabb_test_us = total_aabb_test_us;
        profile->t_culling_us = profile->t_frustum_extract_us + profile->t_aabb_test_us;
    }

    rlDisableBackfaceCulling();
}
