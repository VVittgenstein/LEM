#include "camera_controller.h"
#include "raymath.h"
#include "rlgl.h"
#include <cmath>
#include <algorithm>

CameraController::CameraController() {
    camera.position = Vector3{60.0f, 60.0f, 60.0f};
    camera.target = orbit_target;
    camera.up = Vector3{0.0f, 1.0f, 0.0f};
    camera.fovy = 45.0f;
    camera.projection = CAMERA_PERSPECTIVE;
}

void CameraController::Setup(Vector3 terrain_center, float max_dim, float max_ground_y, float center_ground_y, const VoxelGrid* grid) {
    grid_ref = grid;
    terrain_max_dim = max_dim;
    terrain_radius = max_dim * 0.7071f;
    max_ground_height = max_ground_y;
    center_ground_height = center_ground_y;

    // Center target is at actual center ground height
    orbit_target = Vector3{terrain_center.x, center_ground_y + 2.0f, terrain_center.z};
    initial_target = orbit_target;

    // Dynamic Far Clipping Plane: far_plane = max(5000.0f, terrain_radius * 8.0f)
    // (At 2048 scale: ~11,584 units, completely prevents background mountain truncation)
    far_plane_distance = std::max(5000.0f, terrain_radius * 8.0f);

    // Adaptive orbit distance limits
    min_orbit_distance = 5.0f;
    max_orbit_distance = std::max(2000.0f, terrain_radius * 6.0f);

    // Optimal bird's-eye macroscopic view distance to comfortably fit entire terrain in 45 deg FOV
    orbit_distance = std::clamp(max_dim * 1.85f, min_orbit_distance, max_orbit_distance);
    initial_distance = orbit_distance;

    orbit_yaw = 0.785f;  // 45 degrees diagonal
    orbit_pitch = 0.62f; // ~35.5 degrees elevation

    // Base fly speed scaled with terrain dimensions
    fly_speed = std::clamp(max_dim * 0.15f, 25.0f, 300.0f);

    Reset();
}

void CameraController::ApplyCustomProjection(float aspect) const {
    rlMatrixMode(RL_PROJECTION);
    rlLoadIdentity();
    double top = 0.5 * std::tan(camera.fovy * 0.5 * DEG2RAD);
    double right = top * aspect;
    rlFrustum(-right, right, -top, top, 0.5, far_plane_distance);
    rlMatrixMode(RL_MODELVIEW);
}

void CameraController::EnsureAboveGround(float margin) {
    if (grid_ref != nullptr) {
        int gx = static_cast<int>(camera.position.x);
        int gz = static_cast<int>(camera.position.z);
        int gy = grid_ref->GetGroundHeightAt(gx, gz);
        if (camera.position.y < gy + margin) {
            camera.position.y = gy + margin;
        }
    } else {
        if (camera.position.y < margin) {
            camera.position.y = margin;
        }
    }
}

void CameraController::Reset() {
    orbit_target = initial_target;
    orbit_distance = initial_distance;
    orbit_yaw = 0.785f;
    orbit_pitch = 0.62f;

    // Calculate initial camera position
    float cx = orbit_target.x + orbit_distance * std::cos(orbit_pitch) * std::sin(orbit_yaw);
    float cy = orbit_target.y + orbit_distance * std::sin(orbit_pitch);
    float cz = orbit_target.z + orbit_distance * std::cos(orbit_pitch) * std::cos(orbit_yaw);

    // Safeguard: Ensure camera initial altitude is comfortably above highest peak
    float safe_min_y = max_ground_height + std::max(25.0f, terrain_max_dim * 0.25f);
    if (cy < safe_min_y) {
        cy = safe_min_y;
        float dy = cy - orbit_target.y;
        orbit_distance = std::clamp(dy / std::sin(orbit_pitch), min_orbit_distance, max_orbit_distance);
        cx = orbit_target.x + orbit_distance * std::cos(orbit_pitch) * std::sin(orbit_yaw);
        cz = orbit_target.z + orbit_distance * std::cos(orbit_pitch) * std::cos(orbit_yaw);
    }

    camera.position = Vector3{cx, cy, cz};
    camera.target = orbit_target;

    fly_yaw = orbit_yaw + 3.14159f;
    fly_pitch = -orbit_pitch;

    EnsureAboveGround(5.0f);
}

void CameraController::ToggleMode() {
    if (mode == CAM_ORBIT) {
        SetMode(CAM_FLYCAM);
    } else {
        SetMode(CAM_ORBIT);
    }
}

void CameraController::SetMode(VoxelCameraMode new_mode) {
    if (mode == new_mode) return;

    if (new_mode == CAM_FLYCAM) {
        // Transition from Orbit to Flycam: preserve position and view orientation
        Vector3 forward = Vector3Normalize(Vector3Subtract(camera.target, camera.position));
        fly_pitch = std::asin(std::clamp(forward.y, -0.99f, 0.99f));
        fly_yaw = std::atan2(forward.x, forward.z);
        EnsureAboveGround(5.0f);
    } else {
        // Transition from Flycam to Orbit: project target forward along look vector
        Vector3 forward{
            std::cos(fly_pitch) * std::sin(fly_yaw),
            std::sin(fly_pitch),
            std::cos(fly_pitch) * std::cos(fly_yaw)
        };
        orbit_target = Vector3Add(camera.position, Vector3Scale(forward, orbit_distance));
        orbit_yaw = fly_yaw + 3.14159f;
        orbit_pitch = -fly_pitch;
        orbit_pitch = std::clamp(orbit_pitch, 0.05f, 1.50f);
    }
    mode = new_mode;
}

const char* CameraController::GetModeName() const {
    switch (mode) {
        case CAM_ORBIT:
            return "Orbit / Turntable (Mouse LMB: Rotate, MMB/RMB: Pan, Wheel: Zoom)";
        case CAM_FLYCAM:
            return is_sprinting ? "Flycam [BOOST x10] (WASD: Move, Space/Shift: Up/Down, Ctrl: Boost)"
                                : "Flycam / FPV (WASD: Move, Space/Shift: Up/Down, Ctrl: Boost x10)";
        default:
            return "Unknown";
    }
}

void CameraController::Update(float dt) {
    if (mode == CAM_ORBIT) {
        UpdateOrbit(dt);
    } else {
        UpdateFlycam(dt);
    }
}

void CameraController::UpdateOrbit(float dt) {
    Vector2 mouse_delta = GetMouseDelta();

    // Rotate with Left Mouse Button
    if (IsMouseButtonDown(MOUSE_BUTTON_LEFT) && !IsKeyDown(KEY_LEFT_SHIFT)) {
        orbit_yaw -= mouse_delta.x * 0.005f;
        orbit_pitch += mouse_delta.y * 0.005f;
        orbit_pitch = std::clamp(orbit_pitch, 0.05f, 1.52f);
    }

    // Pan with Middle Mouse Button OR Right Mouse Button OR Shift+Left Click
    if (IsMouseButtonDown(MOUSE_BUTTON_MIDDLE) || IsMouseButtonDown(MOUSE_BUTTON_RIGHT) ||
        (IsMouseButtonDown(MOUSE_BUTTON_LEFT) && IsKeyDown(KEY_LEFT_SHIFT))) {

        Vector3 forward = Vector3Normalize(Vector3Subtract(orbit_target, camera.position));
        Vector3 right = Vector3Normalize(Vector3CrossProduct(forward, camera.up));
        Vector3 up = Vector3Normalize(Vector3CrossProduct(right, forward));

        float pan_speed = orbit_distance * 0.0015f;
        Vector3 pan_offset = Vector3Add(
            Vector3Scale(right, -mouse_delta.x * pan_speed),
            Vector3Scale(up, mouse_delta.y * pan_speed)
        );
        orbit_target = Vector3Add(orbit_target, pan_offset);
    }

    // Zoom with Mouse Wheel (Dynamic clamp adapted to terrain scale!)
    float wheel = GetMouseWheelMove();
    if (wheel != 0.0f) {
        orbit_distance -= wheel * (orbit_distance * 0.10f);
        orbit_distance = std::clamp(orbit_distance, min_orbit_distance, max_orbit_distance);
    }

    // Update Camera3D
    float cx = orbit_target.x + orbit_distance * std::cos(orbit_pitch) * std::sin(orbit_yaw);
    float cy = orbit_target.y + orbit_distance * std::sin(orbit_pitch);
    float cz = orbit_target.z + orbit_distance * std::cos(orbit_pitch) * std::cos(orbit_yaw);

    camera.position = Vector3{cx, cy, cz};
    camera.target = orbit_target;
}

void CameraController::UpdateFlycam(float dt) {
    Vector2 mouse_delta = GetMouseDelta();

    // Look rotation with Right Mouse Button (or Left Mouse Button in Flycam)
    if (IsMouseButtonDown(MOUSE_BUTTON_RIGHT) || IsMouseButtonDown(MOUSE_BUTTON_LEFT)) {
        fly_yaw -= mouse_delta.x * mouse_sensitivity;
        fly_pitch -= mouse_delta.y * mouse_sensitivity;
        fly_pitch = std::clamp(fly_pitch, -1.50f, 1.50f);
    }

    // Adjust base fly speed with mouse wheel
    float wheel = GetMouseWheelMove();
    if (wheel != 0.0f) {
        fly_speed += wheel * 10.0f;
        fly_speed = std::clamp(fly_speed, 5.0f, 600.0f);
    }

    // 10x SPRINT BOOST: Holding Left or Right Control multiplies movement speed by 10
    is_sprinting = IsKeyDown(KEY_LEFT_CONTROL) || IsKeyDown(KEY_RIGHT_CONTROL);
    float current_speed = fly_speed * (is_sprinting ? 10.0f : 1.0f);

    // Current 3D look direction for target
    Vector3 look_dir{
        std::cos(fly_pitch) * std::sin(fly_yaw),
        std::sin(fly_pitch),
        std::cos(fly_pitch) * std::cos(fly_yaw)
    };

    // Horizontal forward vector (world XZ plane, y = 0)
    Vector3 forward_h{look_dir.x, 0.0f, look_dir.z};
    if (Vector3Length(forward_h) > 0.0001f) {
        forward_h = Vector3Normalize(forward_h);
    } else {
        forward_h = Vector3{std::sin(fly_yaw), 0.0f, std::cos(fly_yaw)};
    }

    // Raylib Standard Cross Product: Horizontal Right = Forward x Up
    Vector3 right_h = Vector3Normalize(Vector3CrossProduct(forward_h, Vector3{0.0f, 1.0f, 0.0f}));

    Vector3 move_dir{0, 0, 0};
    if (IsKeyDown(KEY_W)) move_dir = Vector3Add(move_dir, forward_h);
    if (IsKeyDown(KEY_S)) move_dir = Vector3Subtract(move_dir, forward_h);
    if (IsKeyDown(KEY_D)) move_dir = Vector3Add(move_dir, right_h);     // D: move RIGHT
    if (IsKeyDown(KEY_A)) move_dir = Vector3Subtract(move_dir, right_h);  // A: move LEFT

    // Vertical movement: Space = Up (+Y), Left Shift = Down (-Y)
    // Control is exclusively dedicated to x10 Sprint Boost
    if (IsKeyDown(KEY_SPACE)) move_dir.y += 1.0f;
    if (IsKeyDown(KEY_LEFT_SHIFT)) move_dir.y -= 1.0f;

    if (Vector3Length(move_dir) > 0.001f) {
        move_dir = Vector3Normalize(move_dir);
        camera.position = Vector3Add(camera.position, Vector3Scale(move_dir, current_speed * dt));
    }

    EnsureAboveGround(2.0f);
    camera.target = Vector3Add(camera.position, look_dir);
}
