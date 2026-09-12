#pragma once

#include <chrono>

struct FrameProfile {
    // Stage timings in microseconds (us)
    float t_input_us = 0.0f;
    float t_camera_us = 0.0f;
    float t_render3d_us = 0.0f;
    float t_frustum_extract_us = 0.0f; // Frustum plane extraction from camera view-projection
    float t_aabb_test_us = 0.0f;        // Submesh AABB ContainsBox intersection tests
    float t_culling_us = 0.0f;          // Total culling time: extract + AABB tests
    float t_hud_us = 0.0f;
    float t_present_us = 0.0f;          // Time in EndDrawing() including GPU VSync / WaitTime

    // Overall metrics
    float t_frame_total_ms = 0.0f;
    float fps = 0.0f;

    // Culling stats
    int total_submeshes = 0;
    int visible_submeshes = 0;
    int culled_submeshes = 0;

    // Settings
    bool frustum_culling_enabled = true;
    bool backface_culling_enabled = true;
    int fps_mode = 0; // 0: Uncapped (Fastest), 1: 60 FPS, 2: 144 FPS
};

class TimeProbe {
public:
    inline void Start() {
        start_time = std::chrono::high_resolution_clock::now();
    }
    inline float StopUs() {
        auto end_time = std::chrono::high_resolution_clock::now();
        return std::chrono::duration<float, std::micro>(end_time - start_time).count();
    }
    inline float StopMs() {
        auto end_time = std::chrono::high_resolution_clock::now();
        return std::chrono::duration<float, std::milli>(end_time - start_time).count();
    }
private:
    std::chrono::high_resolution_clock::time_point start_time;
};
