#include "raylib.h"
#include "rlgl.h"
#include "raymath.h"
#include "core/fastscape_loader.h"
#include "core/voxel_grid.h"
#include "core/palette_manager.h"
#include "core/voxel_mesher.h"
#include "core/camera_controller.h"
#include "core/hud.h"
#include "core/profiler.h"

#include <iostream>
#include <vector>
#include <string>
#include <filesystem>
#include <chrono>
#include <cmath>

namespace fs = std::filesystem;

// Headless test runner function for CI / automated validation
int RunHeadlessVerification(const std::string& sample_path) {
    std::cout << "==================================================" << std::endl;
    std::cout << " RUNNING HEADLESS VOXEL TERRAIN VALIDATION TEST" << std::endl;
    std::cout << "==================================================" << std::endl;

    FastscapeData data;
    bool loaded = FastscapeLoader::LoadFromFile(sample_path, data);
    if (!loaded) {
        std::cout << "[Test] File not found or invalid, testing procedural generation fallback..." << std::endl;
        loaded = FastscapeLoader::GenerateProceduralSample(64, 64, data);
    }

    if (!loaded || !data.is_valid) {
        std::cerr << "[Test FAILED] Could not obtain valid Fastscape data." << std::endl;
        return 1;
    }
    std::cout << "[Test PASSED] Fastscape data loaded: "
              << data.header.nx << "x" << data.header.ny
              << ", Elevation range: [" << data.header.h_min << ", " << data.header.h_max << "]" << std::endl;

    // Test RTN Quantization
    VoxelGrid grid;
    bool quant_ok = grid.QuantizeFromFastscape(data, 36, 2);
    if (!quant_ok || grid.CountSolidVoxels() == 0) {
        std::cerr << "[Test FAILED] RTN Quantization produced 0 solid voxels." << std::endl;
        return 1;
    }
    std::cout << "[Test PASSED] RTN Quantization OK: "
              << grid.CountSolidVoxels() << " solid voxels, "
              << grid.CountWaterVoxels() << " water voxels." << std::endl;

    // Test Palette Manager
    PaletteManager palette;
    palette.SetupDefaults();
    palette.SetScheme(SCHEME_BIOME);
    std::cout << "[Test PASSED] Palette Manager initialized with scheme: "
              << palette.GetCurrentSchemeName() << std::endl;

    // Test Raylib Headless Window initialization for OpenGL buffer validation
    InitWindow(100, 100, "Headless Test");
    SetTargetFPS(60);

    VoxelMesher mesher;
    bool mesh_ok = mesher.BuildMesh(grid, palette);
    if (!mesh_ok) {
        std::cerr << "[Test FAILED] VoxelMesher failed to construct mesh." << std::endl;
        CloseWindow();
        return 1;
    }

    std::cout << "[Test PASSED] VoxelMesher produced: "
              << mesher.stats.optimized_quads << " quads ("
              << mesher.stats.reduction_percentage << "% reduction) with "
              << mesher.stats.draw_calls << " draw call(s)." << std::endl;

    int max_allowed_draw_calls = (data.header.nx <= 128) ? 2 : 256;
    if (mesher.stats.draw_calls > max_allowed_draw_calls) {
        std::cerr << "[Test FAILED] Draw calls exceed limit (expected <= "
                  << max_allowed_draw_calls << ", got " << mesher.stats.draw_calls << ")." << std::endl;
        CloseWindow();
        return 1;
    }

    // Test color updating
    for (int s = 0; s < SCHEME_COUNT; ++s) {
        palette.SetScheme(static_cast<ColorSchemeType>(s));
        mesher.UpdateColors(grid, palette);
    }
    std::cout << "[Test PASSED] All 4 color schemes tested and vertex colors updated successfully." << std::endl;

    // Test culling statistics conservation in headless mode
    FrameProfile test_prof{};
    test_prof.frustum_culling_enabled = true;
    test_prof.total_submeshes = mesher.stats.submesh_count;
    test_prof.visible_submeshes = 0;
    test_prof.culled_submeshes = 0;

    Camera3D test_cam{};
    test_cam.position = Vector3{100.0f, 100.0f, 100.0f};
    test_cam.target = Vector3{0.0f, 0.0f, 0.0f};
    test_cam.up = Vector3{0.0f, 1.0f, 0.0f};
    test_cam.fovy = 45.0f;

    BeginDrawing();
    mesher.Draw(Vector3{0, 0, 0}, 1.0f, &test_cam, 1.0f, &test_prof);
    EndDrawing();

    if (test_prof.visible_submeshes + test_prof.culled_submeshes != test_prof.total_submeshes) {
        std::cerr << "[Test FAILED] Culling stats non-conservation: visible("
                  << test_prof.visible_submeshes << ") + culled(" << test_prof.culled_submeshes
                  << ") != total(" << test_prof.total_submeshes << ")" << std::endl;
        CloseWindow();
        return 1;
    }
    std::cout << "[Test PASSED] Culling statistics verified: "
              << test_prof.visible_submeshes << " visible + "
              << test_prof.culled_submeshes << " culled = "
              << test_prof.total_submeshes << " total (Extract: "
              << test_prof.t_frustum_extract_us << " us, AABB: "
              << test_prof.t_aabb_test_us << " us)." << std::endl;

    test_prof.t_frame_total_ms = 16.667f;
    test_prof.fps = 60.0f;

    CloseWindow();
    std::cout << "==================================================" << std::endl;
    std::cout << " ALL VERIFICATION TESTS PASSED SUCCESSFULLY!" << std::endl;
    std::cout << "==================================================" << std::endl;
    return 0;
}

// Benchmark runner function for deep performance evaluation
int RunBenchmark(const std::string& terrain_path) {
    std::cout << "\n========================================================" << std::endl;
    std::cout << " DEEP PERFORMANCE BENCHMARK: FASTSCAPE VOXEL TERRAIN" << std::endl;
    std::cout << " Dataset: " << terrain_path << std::endl;
    std::cout << "========================================================" << std::endl;

    auto t0 = std::chrono::high_resolution_clock::now();
    FastscapeData data;
    bool loaded = FastscapeLoader::LoadFromFile(terrain_path, data);
    if (!loaded) {
        std::cerr << "[Benchmark FAILED] Could not open " << terrain_path << std::endl;
        return 1;
    }
    auto t1 = std::chrono::high_resolution_clock::now();
    float load_time_ms = std::chrono::duration<float, std::milli>(t1 - t0).count();

    // 1. RTN Quantization
    auto t_q0 = std::chrono::high_resolution_clock::now();
    VoxelGrid grid;
    bool quant_ok = grid.QuantizeFromFastscape(data, 36, 2);
    auto t_q1 = std::chrono::high_resolution_clock::now();
    float quant_time_ms = std::chrono::duration<float, std::milli>(t_q1 - t_q0).count();
    if (!quant_ok) return 1;

    // 2. Setup Palette
    PaletteManager palette;
    palette.SetupDefaults();

    // 3. Initialize Window for OpenGL
    SetConfigFlags(FLAG_WINDOW_HIDDEN);
    InitWindow(1280, 720, "Benchmark Window");
    SetTargetFPS(0); // Uncapped FPS for benchmark

    // 4. Greedy Meshing & GPU Upload
    auto t_m0 = std::chrono::high_resolution_clock::now();
    VoxelMesher mesher;
    bool mesh_ok = mesher.BuildMesh(grid, palette);
    auto t_m1 = std::chrono::high_resolution_clock::now();
    float mesh_time_ms = std::chrono::duration<float, std::milli>(t_m1 - t_m0).count();
    if (!mesh_ok) {
        CloseWindow();
        return 1;
    }

    // 5. Benchmark Color Scheme Updates
    auto t_c0 = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < 4; ++i) {
        palette.SetScheme(static_cast<ColorSchemeType>(i));
        mesher.UpdateColors(grid, palette);
    }
    auto t_c1 = std::chrono::high_resolution_clock::now();
    float color_update_ms = std::chrono::duration<float, std::milli>(t_c1 - t_c0).count() / 4.0f;

    // 6. Camera setup & Rendering benchmark (120 frames)
    Camera3D camera{};
    float safe_y = grid.GetMaxGroundHeight() + 20.0f;
    float safe_dist = std::max(grid.size_x, grid.size_z) * 1.5f;
    camera.position = Vector3{grid.size_x * 0.5f + safe_dist * 0.7f, safe_y, grid.size_z * 0.5f + safe_dist * 0.7f};
    camera.target = Vector3{grid.size_x * 0.5f, grid.GetCenterGroundHeight(), grid.size_z * 0.5f};
    camera.up = Vector3{0.0f, 1.0f, 0.0f};
    camera.fovy = 45.0f;
    camera.projection = CAMERA_PERSPECTIVE;

    FrameProfile profile{};
    profile.frustum_culling_enabled = true;
    profile.total_submeshes = mesher.stats.submesh_count;

    float far_plane = std::max(5000.0f, std::max(grid.size_x, grid.size_z) * 0.7071f * 8.0f);

    const int benchmark_frames = 120;
    auto t_r0 = std::chrono::high_resolution_clock::now();
    for (int frame = 0; frame < benchmark_frames; ++frame) {
        profile.visible_submeshes = 0;
        profile.culled_submeshes = 0;

        BeginDrawing();
        ClearBackground(DARKGRAY);
        BeginMode3D(camera);

        // Apply custom projection with dynamic far clipping plane
        rlMatrixMode(RL_PROJECTION);
        rlLoadIdentity();
        double top = 0.5 * std::tan(camera.fovy * 0.5 * DEG2RAD);
        double right = top * (1280.0f / 720.0f);
        rlFrustum(-right, right, -top, top, 0.5, far_plane);
        rlMatrixMode(RL_MODELVIEW);

        mesher.Draw(Vector3{0, 0, 0}, 1.0f, &camera, 1280.0f / 720.0f, &profile, far_plane);
        EndMode3D();
        EndDrawing();

        // Verify culling conservation on every frame
        if (profile.visible_submeshes + profile.culled_submeshes != profile.total_submeshes) {
            std::cerr << "[Benchmark ERROR] Culling conservation failed! Visible ("
                      << profile.visible_submeshes << ") + Culled (" << profile.culled_submeshes
                      << ") != Total (" << profile.total_submeshes << ")" << std::endl;
            CloseWindow();
            return 1;
        }
    }
    auto t_r1 = std::chrono::high_resolution_clock::now();
    float render_total_ms = std::chrono::duration<float, std::milli>(t_r1 - t_r0).count();
    float avg_frame_time_ms = render_total_ms / benchmark_frames;
    float avg_fps = 1000.0f / avg_frame_time_ms;

    // Synchronize FrameProfile metrics
    profile.t_frame_total_ms = avg_frame_time_ms;
    profile.fps = avg_fps;

    CloseWindow();

    // Print Detailed Structured Benchmark Report
    std::cout << "\n--------------------------------------------------------" << std::endl;
    std::cout << " PERFORMANCE EVALUATION SUMMARY (" << data.header.nx << "x" << data.header.ny << " Scale)" << std::endl;
    std::cout << "--------------------------------------------------------" << std::endl;
    std::cout << " 1. Grid Dimensions:       " << data.header.nx << " x " << data.header.ny << " ("
              << (data.header.nx * data.header.ny) << " elevation points)" << std::endl;
    std::cout << " 2. Elevation Range:       [" << data.header.h_min << ", " << data.header.h_max << "] m" << std::endl;
    std::cout << " 3. Solid Voxels:          " << mesher.stats.total_solid_voxels << std::endl;
    std::cout << " 4. File Loading Time:     " << load_time_ms << " ms" << std::endl;
    std::cout << " 5. RTN Quantization Time: " << quant_time_ms << " ms" << std::endl;
    std::cout << " 6. Parallel Greedy Mesh:  " << mesh_time_ms << " ms" << std::endl;
    std::cout << " 7. Unoptimized Faces:     " << mesher.stats.unoptimized_faces << std::endl;
    std::cout << " 8. Optimized Quads:       " << mesher.stats.optimized_quads << std::endl;
    std::cout << " 9. Face Reduction Ratio:  " << mesher.stats.reduction_percentage << " %" << std::endl;
    std::cout << "10. Total Triangles:       " << (mesher.stats.terrain_triangles + mesher.stats.water_triangles) << std::endl;
    std::cout << "11. Submeshes / Draw Calls:" << mesher.stats.draw_calls << " (16-bit vertex index limit safe)" << std::endl;
    std::cout << "    Culling Conservation:  " << profile.visible_submeshes << " visible + "
              << profile.culled_submeshes << " culled = " << profile.total_submeshes
              << " total (100% strictly closed)" << std::endl;
    std::cout << "    Frustum Extract Time:  " << profile.t_frustum_extract_us << " us" << std::endl;
    std::cout << "    Submesh AABB Test Time:" << profile.t_aabb_test_us << " us ("
              << profile.total_submeshes << " AABB tests)" << std::endl;
    std::cout << "12. GPU VRAM Consumption:  " << (mesher.stats.memory_vram_bytes / (1024.0f * 1024.0f)) << " MB" << std::endl;
    std::cout << "13. CPU RAM Consumption:   " << (mesher.stats.memory_ram_bytes / (1024.0f * 1024.0f)) << " MB" << std::endl;
    std::cout << "14. Color Scheme Switch:   " << color_update_ms << " ms / update (GPU buffer stream)" << std::endl;
    std::cout << "15. Average Render Time:   " << avg_frame_time_ms << " ms / frame" << std::endl;
    std::cout << "16. Average Render FPS:    " << avg_fps << " FPS" << std::endl;
    std::cout << "========================================================\n" << std::endl;

    return 0;
}

int main(int argc, char* argv[]) {
    std::vector<std::string> terrain_files = {
        "resources/sample_terrain.flem",
        "resources/mountain_terrain.flem",
        "resources/terrain_2048_eroded.flem",
        "resources/terrain_2048.flem"
    };
    std::string current_terrain = terrain_files[0];
    std::string palette_file = "resources/palette.ini";

    // CLI argument parsing
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--test" || arg == "-t" || arg == "--headless") {
            return RunHeadlessVerification(current_terrain);
        } else if (arg == "--benchmark" || arg == "-b") {
            return RunBenchmark(current_terrain);
        } else if (arg == "--help" || arg == "-h") {
            std::cout << "Usage: " << argv[0] << " [options] [path_to_terrain.flem]" << std::endl;
            std::cout << "Options:" << std::endl;
            std::cout << "  --benchmark, -b Run deep performance benchmark and exit" << std::endl;
            std::cout << "  --test, -t      Run automated headless verification and exit" << std::endl;
            std::cout << "  --help, -h      Show this help message" << std::endl;
            return 0;
        } else if (arg.rfind(".flem") != std::string::npos || arg.rfind(".bin") != std::string::npos) {
            current_terrain = arg;
        }
    }

    // Check fallback if running from build directory
    if (!fs::exists(current_terrain) && fs::exists("../" + current_terrain)) {
        for (auto& tf : terrain_files) tf = "../" + tf;
        current_terrain = "../" + current_terrain;
        palette_file = "../resources/palette.ini";
    }

    // Initialize window
    const int screen_width = 1280;
    const int screen_height = 720;
    SetConfigFlags(FLAG_WINDOW_RESIZABLE | FLAG_MSAA_4X_HINT);
    InitWindow(screen_width, screen_height, "Fastscape Voxel Terrain Preview [Raylib]");
    SetTargetFPS(0); // Default to uncapped for maximum responsiveness; switchable via 'V'

    // Initialize components
    PaletteManager palette;
    palette.LoadFromIni(palette_file);

    FastscapeData fastscape_data;
    std::string current_name = fs::path(current_terrain).filename().string();
    if (!FastscapeLoader::LoadFromFile(current_terrain, fastscape_data)) {
        std::cout << "[App] Loading fallback procedural terrain..." << std::endl;
        FastscapeLoader::GenerateProceduralSample(64, 64, fastscape_data);
        current_name = "Procedural Sample (64x64)";
    }

    VoxelGrid voxel_grid;
    voxel_grid.QuantizeFromFastscape(fastscape_data, palette.voxel_height_steps, palette.water_level_voxels);

    VoxelMesher mesher;
    mesher.BuildMesh(voxel_grid, palette);

    // Center camera on the terrain with optimal bird's-eye macroscopic view
    Vector3 terrain_center{
        voxel_grid.size_x * 0.5f,
        voxel_grid.GetCenterGroundHeight(),
        voxel_grid.size_z * 0.5f
    };
    float max_dim = static_cast<float>(std::max(voxel_grid.size_x, voxel_grid.size_z));

    CameraController camera_ctrl;
    camera_ctrl.Setup(terrain_center, max_dim,
                      static_cast<float>(voxel_grid.GetMaxGroundHeight()),
                      voxel_grid.GetCenterGroundHeight(),
                      &voxel_grid);

    HUD hud;
    FrameProfile profile{};
    profile.frustum_culling_enabled = true;
    profile.backface_culling_enabled = true;
    profile.fps_mode = 0; // Uncapped by default

    bool show_grid = false; // Grid disabled by default on large terrains to eliminate 32k immediate-mode draw call stalls
    int current_dataset_idx = 0;

    // Helper lambda to reload new terrain dataset
    auto LoadTerrainFile = [&](const std::string& path) {
        if (FastscapeLoader::LoadFromFile(path, fastscape_data)) {
            current_name = fs::path(path).filename().string();
            voxel_grid.QuantizeFromFastscape(fastscape_data, palette.voxel_height_steps, palette.water_level_voxels);
            mesher.BuildMesh(voxel_grid, palette);

            Vector3 center{
                voxel_grid.size_x * 0.5f,
                voxel_grid.GetCenterGroundHeight(),
                voxel_grid.size_z * 0.5f
            };
            float new_max_dim = static_cast<float>(std::max(voxel_grid.size_x, voxel_grid.size_z));
            camera_ctrl.Setup(center, new_max_dim,
                              static_cast<float>(voxel_grid.GetMaxGroundHeight()),
                              voxel_grid.GetCenterGroundHeight(),
                              &voxel_grid);
        }
    };

    TimeProbe probe_frame, probe_input, probe_camera, probe_render3d, probe_hud, probe_present;

    // Main render & update loop
    while (!WindowShouldClose()) {
        probe_frame.Start();
        float dt = GetFrameTime();

        // 1. Handle Input & Keybindings
        probe_input.Start();
        if (IsKeyPressed(KEY_TAB) || IsKeyPressed(KEY_M)) {
            camera_ctrl.ToggleMode();
        }
        if (IsKeyPressed(KEY_R)) {
            camera_ctrl.Reset();
        }
        if (IsKeyPressed(KEY_C)) {
            palette.CycleScheme();
            mesher.UpdateColors(voxel_grid, palette);
        }
        if (IsKeyPressed(KEY_ONE)) {
            palette.SetScheme(SCHEME_BIOME);
            mesher.UpdateColors(voxel_grid, palette);
        }
        if (IsKeyPressed(KEY_TWO)) {
            palette.SetScheme(SCHEME_ELEVATION);
            mesher.UpdateColors(voxel_grid, palette);
        }
        if (IsKeyPressed(KEY_THREE)) {
            palette.SetScheme(SCHEME_HYDROLOGY);
            mesher.UpdateColors(voxel_grid, palette);
        }
        if (IsKeyPressed(KEY_FOUR)) {
            palette.SetScheme(SCHEME_EROSION);
            mesher.UpdateColors(voxel_grid, palette);
        }
        if (IsKeyPressed(KEY_P)) {
            palette.LoadFromIni(palette_file);
            mesher.UpdateColors(voxel_grid, palette);
        }
        if (IsKeyPressed(KEY_L)) {
            // Cycle between available datasets
            current_dataset_idx = (current_dataset_idx + 1) % terrain_files.size();
            LoadTerrainFile(terrain_files[current_dataset_idx]);
        }
        if (IsKeyPressed(KEY_H)) {
            hud.ToggleHUD();
        }
        if (IsKeyPressed(KEY_F3)) {
            hud.ToggleProfiler();
        }
        if (IsKeyPressed(KEY_F)) {
            profile.frustum_culling_enabled = !profile.frustum_culling_enabled;
        }
        if (IsKeyPressed(KEY_V)) {
            profile.fps_mode = (profile.fps_mode + 1) % 3;
            SetTargetFPS((profile.fps_mode == 0) ? 0 : ((profile.fps_mode == 1) ? 60 : 144));
        }
        if (IsKeyPressed(KEY_G)) {
            show_grid = !show_grid;
        }
        if (IsKeyPressed(KEY_F11)) {
            ToggleFullscreen();
        }

        // Support drag and drop .flem files directly onto the window
        if (IsFileDropped()) {
            FilePathList dropped_files = LoadDroppedFiles();
            if (dropped_files.count > 0) {
                LoadTerrainFile(dropped_files.paths[0]);
            }
            UnloadDroppedFiles(dropped_files);
        }
        profile.t_input_us = probe_input.StopUs();

        // 2. Update Camera
        probe_camera.Start();
        camera_ctrl.Update(dt);
        profile.t_camera_us = probe_camera.StopUs();

        // 3. Render 3D Scene
        BeginDrawing();
        ClearBackground(Color{22, 26, 32, 255}); // Modern dark slate

        float aspect = static_cast<float>(GetScreenWidth()) / static_cast<float>(GetScreenHeight());
        profile.total_submeshes = mesher.stats.submesh_count;
        profile.visible_submeshes = 0;
        profile.culled_submeshes = 0;

        BeginMode3D(camera_ctrl.camera);
        // Apply dynamic far clipping plane to prevent any distant terrain cutoff
        camera_ctrl.ApplyCustomProjection(aspect);

        probe_render3d.Start();
        // Draw terrain with frustum culling & hardware backface culling
        mesher.Draw(Vector3{0.0f, 0.0f, 0.0f}, 1.0f, &camera_ctrl.camera, aspect, &profile, camera_ctrl.far_plane_distance);
        profile.t_render3d_us = probe_render3d.StopUs();

        // Draw ground reference grid only if enabled (prevents immediate mode stall)
        if (show_grid) {
            DrawGrid(32, 16.0f);
        }

        EndMode3D();

        // 4. Render 2D HUD Overlay & Profiler
        probe_hud.Start();
        hud.Draw(camera_ctrl, palette, mesher, voxel_grid, profile, current_name,
                 GetScreenWidth(), GetScreenHeight());
        profile.t_hud_us = probe_hud.StopUs();

        // 5. Present Frame & SwapBuffers
        probe_present.Start();
        EndDrawing();
        profile.t_present_us = probe_present.StopUs();

        profile.t_frame_total_ms = probe_frame.StopMs();
        profile.fps = (profile.t_frame_total_ms > 0.001f) ? (1000.0f / profile.t_frame_total_ms) : static_cast<float>(GetFPS());
    }

    // Cleanup
    mesher.Unload();
    CloseWindow();
    return 0;
}
