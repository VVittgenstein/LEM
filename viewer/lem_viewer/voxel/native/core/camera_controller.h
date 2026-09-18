#pragma once

#include "raylib.h"
#include "voxel_grid.h"

enum VoxelCameraMode {
    CAM_ORBIT = 0,
    CAM_FLYCAM = 1,
    CAM_MODE_COUNT
};

class CameraController {
public:
    CameraController();

    Camera3D camera{};
    VoxelCameraMode mode = CAM_ORBIT;

    // Orbit parameters
    Vector3 orbit_target{32.0f, 10.0f, 32.0f};
    float orbit_distance = 90.0f;
    float orbit_yaw = 0.785f;     // 45 degrees
    float orbit_pitch = 0.62f;    // ~35.5 degrees

    // Dynamic distance limits (auto-adapted to terrain scale)
    float min_orbit_distance = 0.05f;
    float max_orbit_distance = 25000.0f;

    // Dynamic Far Clipping Plane (prevents far terrain truncation)
    float far_plane_distance = 5000.0f;

    // Terrain metrics for adaptive positioning and anti-penetration
    float max_ground_height = 40.0f;
    float center_ground_height = 10.0f;
    float terrain_radius = 45.0f;
    float terrain_max_dim = 64.0f;
    const VoxelGrid* grid_ref = nullptr;

    // Flycam parameters
    float fly_yaw = 0.785f;
    float fly_pitch = -0.5f;
    float fly_speed = 35.0f;
    bool is_sprinting = false;    // True when Ctrl is pressed (x10 speed)
    float mouse_sensitivity = 0.003f;

    void Setup(Vector3 terrain_center, float max_dim, float max_ground_y = 40.0f, float center_ground_y = 10.0f, const VoxelGrid* grid = nullptr);
    void SetGrid(const VoxelGrid* grid) { grid_ref = grid; }
    void Update(float delta_time);
    void Zoom(float wheel);
    void ToggleMode();
    void SetMode(VoxelCameraMode new_mode);
    void Reset();

    // Applies custom projection matrix with dynamic far clipping plane to OpenGL
    void ApplyCustomProjection(float aspect) const;

    float GetEffectiveFlySpeed() const {
        return fly_speed * (is_sprinting ? 10.0f : 1.0f);
    }

    const char* GetModeName() const;

private:
    Vector3 initial_target{32.0f, 10.0f, 32.0f};
    float initial_distance = 90.0f;
    bool is_dragging_orbit = false;
    bool is_panning_orbit = false;
    Vector2 last_mouse_pos{0, 0};

    void UpdateOrbit(float dt);
    void UpdateFlycam(float dt);
    void EnsureAboveGround(float margin = 3.0f);
};
