#pragma once

#include "raylib.h"
#include "camera_controller.h"
#include "palette_manager.h"
#include "voxel_mesher.h"
#include "voxel_grid.h"
#include "profiler.h"
#include <string>

class HUD {
public:
    HUD() = default;

    bool show_hud = true;
    bool show_help = true;
    bool show_profiler = false;

    void Draw(const CameraController& cam,
              const PaletteManager& palette,
              const VoxelMesher& mesher,
              const VoxelGrid& grid,
              const FrameProfile& profile,
              const std::string& current_dataset_name,
              int screen_width, int screen_height);

    void ToggleHUD() { show_hud = !show_hud; }
    void ToggleHelp() { show_help = !show_help; }
    void ToggleProfiler() { show_profiler = !show_profiler; }
};
