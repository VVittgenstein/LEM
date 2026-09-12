#include "hud.h"
#include <cstdio>
#include <string>

void HUD::Draw(const CameraController& cam,
               const PaletteManager& palette,
               const VoxelMesher& mesher,
               const VoxelGrid& grid,
               const FrameProfile& profile,
               const std::string& current_dataset_name,
               int screen_width, int screen_height) {
    if (!show_hud) {
        DrawText("Press 'H' to show HUD | 'F3' for Profiler", 10, 10, 16, Fade(WHITE, 0.7f));
        return;
    }

    // 1. Top-left Main Status Panel
    int panel_x = 12;
    int panel_y = 12;
    int panel_w = 410;
    int panel_h = 250;

    DrawRectangle(panel_x, panel_y, panel_w, panel_h, Fade(BLACK, 0.76f));
    DrawRectangleLines(panel_x, panel_y, panel_w, panel_h, Fade(SKYBLUE, 0.5f));

    int y_cursor = panel_y + 10;
    DrawText("FASTSCAPE VOXEL TERRAIN VIEWER", panel_x + 12, y_cursor, 18, GOLD);
    y_cursor += 24;

    char buf[128];
    // FPS & Draw calls
    int fps = GetFPS();
    float frame_time = profile.t_frame_total_ms;
    std::snprintf(buf, sizeof(buf), "FPS: %d (%.2f ms) | Draw Calls: %d / %d",
                  fps, frame_time, profile.visible_submeshes, profile.total_submeshes);
    DrawText(buf, panel_x + 12, y_cursor, 15, LIME);
    y_cursor += 20;

    // Dataset info
    std::snprintf(buf, sizeof(buf), "Dataset: %s (%dx%d)",
                  current_dataset_name.c_str(), grid.size_x, grid.size_z);
    DrawText(buf, panel_x + 12, y_cursor, 14, RAYWHITE);
    y_cursor += 18;

    // Camera Mode & Far clipping distance
    if (cam.mode == CAM_ORBIT) {
        std::snprintf(buf, sizeof(buf), "Camera: ORBIT | FarPlane: %.0f", cam.far_plane_distance);
        DrawText(buf, panel_x + 12, y_cursor, 14, SKYBLUE);
    } else {
        if (cam.is_sprinting) {
            std::snprintf(buf, sizeof(buf), "Camera: FLYCAM [BOOST x10] (Spd: %.0f) | Far: %.0f",
                          cam.GetEffectiveFlySpeed(), cam.far_plane_distance);
            DrawText(buf, panel_x + 12, y_cursor, 14, GREEN);
        } else {
            std::snprintf(buf, sizeof(buf), "Camera: FLYCAM (Spd: %.0f) | Far: %.0f",
                          cam.GetEffectiveFlySpeed(), cam.far_plane_distance);
            DrawText(buf, panel_x + 12, y_cursor, 14, ORANGE);
        }
    }
    y_cursor += 18;

    // Color Scheme
    std::snprintf(buf, sizeof(buf), "Color: %s", palette.GetCurrentSchemeName());
    DrawText(buf, panel_x + 12, y_cursor, 14, YELLOW);
    y_cursor += 20;

    DrawLine(panel_x + 12, y_cursor, panel_x + panel_w - 12, y_cursor, Fade(GRAY, 0.5f));
    y_cursor += 8;

    std::snprintf(buf, sizeof(buf), "Solid Voxels: %d | Water: %d",
                  mesher.stats.total_solid_voxels, grid.CountWaterVoxels());
    DrawText(buf, panel_x + 12, y_cursor, 13, LIGHTGRAY);
    y_cursor += 16;

    std::snprintf(buf, sizeof(buf), "Faces: %d -> %d Quads (-%.2f%%)",
                  mesher.stats.unoptimized_faces,
                  mesher.stats.optimized_quads,
                  mesher.stats.reduction_percentage);
    DrawText(buf, panel_x + 12, y_cursor, 13, GREEN);
    y_cursor += 16;

    std::snprintf(buf, sizeof(buf), "Triangles: %d | Frustum Culling: %s",
                  mesher.stats.terrain_triangles + mesher.stats.water_triangles,
                  profile.frustum_culling_enabled ? "ON" : "OFF");
    DrawText(buf, panel_x + 12, y_cursor, 13, LIGHTGRAY);

    // 2. High-Precision Profiler Panel (Toggleable via F3)
    if (show_profiler) {
        int prof_w = 400;
        int prof_h = 295;
        int prof_x = panel_x;
        int prof_y = panel_y + panel_h + 10;

        DrawRectangle(prof_x, prof_y, prof_w, prof_h, Fade(Color{15, 23, 42, 255}, 0.88f));
        DrawRectangleLines(prof_x, prof_y, prof_w, prof_h, Fade(LIME, 0.6f));

        int py = prof_y + 10;
        DrawText("SYSTEM PROFILER (Time Probes)", prof_x + 12, py, 16, LIME);
        py += 24;

        std::snprintf(buf, sizeof(buf), "Input & Events:    %6.1f us", profile.t_input_us);
        DrawText(buf, prof_x + 12, py, 13, RAYWHITE); py += 17;

        std::snprintf(buf, sizeof(buf), "Camera Controller: %6.1f us", profile.t_camera_us);
        DrawText(buf, prof_x + 12, py, 13, RAYWHITE); py += 17;

        std::snprintf(buf, sizeof(buf), "Frustum Extract:   %6.1f us", profile.t_frustum_extract_us);
        DrawText(buf, prof_x + 12, py, 13, RAYWHITE); py += 17;

        std::snprintf(buf, sizeof(buf), "Submesh AABB Test: %6.1f us (%d tests)",
                      profile.t_aabb_test_us, profile.total_submeshes);
        DrawText(buf, prof_x + 12, py, 13, RAYWHITE); py += 17;

        std::snprintf(buf, sizeof(buf), "Total Culling:     %6.1f us", profile.t_culling_us);
        DrawText(buf, prof_x + 12, py, 13, RAYWHITE); py += 17;

        std::snprintf(buf, sizeof(buf), "3D Scene DrawModel:%6.2f ms (%d vis + %d cull = %d)",
                      profile.t_render3d_us / 1000.0f,
                      profile.visible_submeshes, profile.culled_submeshes, profile.total_submeshes);
        DrawText(buf, prof_x + 12, py, 13, GOLD); py += 17;

        std::snprintf(buf, sizeof(buf), "2D HUD & Overlay:  %6.1f us", profile.t_hud_us);
        DrawText(buf, prof_x + 12, py, 13, RAYWHITE); py += 17;

        std::snprintf(buf, sizeof(buf), "EndDrawing/Present:%6.2f ms (Wait/VSync)", profile.t_present_us / 1000.0f);
        DrawText(buf, prof_x + 12, py, 13, (profile.t_present_us > 8000.0f) ? ORANGE : RAYWHITE); py += 17;

        DrawLine(prof_x + 12, py, prof_x + prof_w - 12, py, Fade(GRAY, 0.5f)); py += 7;

        const char* cap_mode = (profile.fps_mode == 0) ? "Uncapped (Fastest)" : ((profile.fps_mode == 1) ? "60 FPS Cap" : "144 FPS Cap");
        std::snprintf(buf, sizeof(buf), "FPS Mode [V]: %s | Backface Culling: ON", cap_mode);
        DrawText(buf, prof_x + 12, py, 12, SKYBLUE);
    }

    // 3. Right Panel: Hotkeys & Help
    if (show_help) {
        int help_w = 370;
        int help_h = 245;
        int help_x = screen_width - help_w - 12;
        int help_y = 12;

        DrawRectangle(help_x, help_y, help_w, help_h, Fade(BLACK, 0.76f));
        DrawRectangleLines(help_x, help_y, help_w, help_h, Fade(ORANGE, 0.5f));

        int hy = help_y + 10;
        DrawText("CONTROLS & SHORTCUTS", help_x + 12, hy, 16, ORANGE);
        hy += 22;

        DrawText("[Tab] / [M]   : Toggle Camera (Orbit / Flycam)", help_x + 12, hy, 13, RAYWHITE); hy += 16;
        DrawText("[W/A/S/D]     : Move Horizontal (XZ World Plane)", help_x + 12, hy, 13, RAYWHITE); hy += 16;
        DrawText("[Space]/[Shift: Ascend / Descend (+Y / -Y)", help_x + 12, hy, 13, RAYWHITE); hy += 16;
        DrawText("[Ctrl] (Hold) : Sprint Boost (Speed x10)", help_x + 12, hy, 13, LIME); hy += 16;
        DrawText("[C]           : Cycle Color Scheme", help_x + 12, hy, 13, RAYWHITE); hy += 16;
        DrawText("[1] - [4]     : Direct Color (Biome/Elev/Hydro/Eros)", help_x + 12, hy, 13, RAYWHITE); hy += 16;
        DrawText("[L]           : Switch Terrain Dataset", help_x + 12, hy, 13, RAYWHITE); hy += 16;
        DrawText("[F3]          : Toggle Detailed Profiler", help_x + 12, hy, 13, LIME); hy += 16;
        DrawText("[F]           : Toggle Frustum Culling", help_x + 12, hy, 13, SKYBLUE); hy += 16;
        DrawText("[V]           : Toggle FPS Cap (Uncapped/60/144)", help_x + 12, hy, 13, SKYBLUE); hy += 16;
        DrawText("[G]           : Toggle Reference Grid", help_x + 12, hy, 13, RAYWHITE); hy += 16;
        DrawText("[R] / [P]     : Reset Camera / Reload palette.ini", help_x + 12, hy, 13, RAYWHITE);
    }
}
