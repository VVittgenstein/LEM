#include "fastscape_loader.h"
#include <fstream>
#include <iostream>
#include <cmath>
#include <algorithm>

float FastscapeData::GetNormalizedDrainage(uint32_t x, uint32_t y) const {
    float raw = GetDrainage(x, y);
    if (raw <= 0.0f) return 0.0f;
    float log_val = std::log10(1.0f + raw);
    float log_min = std::log10(1.0f + std::max(0.0f, header.area_min));
    float log_max = std::log10(1.0f + std::max(1.0f, header.area_max));
    if (log_max <= log_min) return 0.0f;
    float norm = (log_val - log_min) / (log_max - log_min);
    return std::clamp(norm, 0.0f, 1.0f);
}

float FastscapeData::GetNormalizedElevation(uint32_t x, uint32_t y) const {
    float raw = GetElevation(x, y);
    float range = header.h_max - header.h_min;
    if (range <= 0.0001f) return 0.5f;
    return std::clamp((raw - header.h_min) / range, 0.0f, 1.0f);
}

float FastscapeData::GetNormalizedErosion(uint32_t x, uint32_t y) const {
    float raw = GetErosion(x, y);
    float range = header.erosion_max - header.erosion_min;
    if (range <= 0.000001f) return 0.5f;
    return std::clamp((raw - header.erosion_min) / range, 0.0f, 1.0f);
}

bool FastscapeLoader::LoadFromFile(const std::string& filepath, FastscapeData& out_data) {
    std::ifstream file(filepath, std::ios::binary);
    if (!file.is_open()) {
        std::cerr << "[FastscapeLoader] Failed to open file: " << filepath << std::endl;
        return false;
    }

    // Read header
    file.read(reinterpret_cast<char*>(&out_data.header), sizeof(FLEMHeader));
    if (file.gcount() != sizeof(FLEMHeader)) {
        std::cerr << "[FastscapeLoader] Truncated header in: " << filepath << std::endl;
        return false;
    }

    // Verify magic
    if (out_data.header.magic[0] != 'F' || out_data.header.magic[1] != 'L' ||
        out_data.header.magic[2] != 'E' || out_data.header.magic[3] != 'M') {
        std::cerr << "[FastscapeLoader] Invalid magic header (expected FLEM)" << std::endl;
        return false;
    }

    if (out_data.header.version != 1) {
        std::cerr << "[FastscapeLoader] Unsupported version: " << out_data.header.version << std::endl;
        return false;
    }

    uint32_t total_points = out_data.header.nx * out_data.header.ny;
    if (total_points == 0 || total_points > 4096 * 4096) {
        std::cerr << "[FastscapeLoader] Invalid dimensions: "
                  << out_data.header.nx << "x" << out_data.header.ny << std::endl;
        return false;
    }

    out_data.elevation.resize(total_points);
    out_data.drainage_area.resize(total_points);
    out_data.erosion_rate.resize(total_points);

    // Read elevation
    file.read(reinterpret_cast<char*>(out_data.elevation.data()), total_points * sizeof(float));
    if (file.gcount() != static_cast<std::streamsize>(total_points * sizeof(float))) {
        std::cerr << "[FastscapeLoader] Failed to read elevation field" << std::endl;
        return false;
    }

    // Read drainage area
    file.read(reinterpret_cast<char*>(out_data.drainage_area.data()), total_points * sizeof(float));
    if (file.gcount() != static_cast<std::streamsize>(total_points * sizeof(float))) {
        std::cerr << "[FastscapeLoader] Failed to read drainage area field" << std::endl;
        return false;
    }

    // Read erosion rate
    file.read(reinterpret_cast<char*>(out_data.erosion_rate.data()), total_points * sizeof(float));
    if (file.gcount() != static_cast<std::streamsize>(total_points * sizeof(float))) {
        std::cerr << "[FastscapeLoader] Failed to read erosion rate field" << std::endl;
        return false;
    }

    out_data.is_valid = true;
    std::cout << "[FastscapeLoader] Successfully loaded: " << filepath << " ("
              << out_data.header.nx << "x" << out_data.header.ny << ")" << std::endl;
    return true;
}

bool FastscapeLoader::GenerateProceduralSample(uint32_t nx, uint32_t ny, FastscapeData& out_data) {
    out_data.header.magic[0] = 'F';
    out_data.header.magic[1] = 'L';
    out_data.header.magic[2] = 'E';
    out_data.header.magic[3] = 'M';
    out_data.header.version = 1;
    out_data.header.nx = nx;
    out_data.header.ny = ny;
    out_data.header.length_x = nx * 200.0f;
    out_data.header.length_y = ny * 200.0f;
    out_data.header.has_water = 1;
    out_data.header.water_level = 2.0f;

    uint32_t total = nx * ny;
    out_data.elevation.resize(total);
    out_data.drainage_area.resize(total);
    out_data.erosion_rate.resize(total);

    float h_min = 1e9f, h_max = -1e9f;
    float a_min = 1e9f, a_max = -1e9f;
    float e_min = 1e9f, e_max = -1e9f;

    for (uint32_t y = 0; y < ny; ++y) {
        for (uint32_t x = 0; x < nx; ++x) {
            float fx = static_cast<float>(x) / nx;
            float fy = static_cast<float>(y) / ny;

            // Synthetic landscape: mountain ridge + drainage valleys
            float ridge = std::sin(fx * 3.14159f) * std::cos(fy * 3.14159f);
            float noise1 = std::sin(fx * 6.28f * 2.0f) * 0.25f + std::cos(fy * 6.28f * 3.0f) * 0.2f;
            float noise2 = std::sin((fx + fy) * 6.28f * 5.0f) * 0.1f;
            float h = std::max(0.0f, (ridge + noise1 + noise2 + 0.3f) * 150.0f);

            // Channel flow accumulation simulation
            float dist_center = std::abs(fx - 0.5f);
            float drainage = 1000.0f / (dist_center * dist_center + 0.05f);
            float erosion = (1.0f - dist_center) * 0.001f;

            uint32_t idx = y * nx + x;
            out_data.elevation[idx] = h;
            out_data.drainage_area[idx] = drainage;
            out_data.erosion_rate[idx] = erosion;

            if (h < h_min) h_min = h;
            if (h > h_max) h_max = h;
            if (drainage < a_min) a_min = drainage;
            if (drainage > a_max) a_max = drainage;
            if (erosion < e_min) e_min = erosion;
            if (erosion > e_max) e_max = erosion;
        }
    }

    out_data.header.h_min = h_min;
    out_data.header.h_max = h_max;
    out_data.header.area_min = a_min;
    out_data.header.area_max = a_max;
    out_data.header.erosion_min = e_min;
    out_data.header.erosion_max = e_max;
    out_data.is_valid = true;
    return true;
}
