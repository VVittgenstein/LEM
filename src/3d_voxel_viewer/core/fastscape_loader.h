#pragma once

#include <string>
#include <vector>
#include <cstdint>

#pragma pack(push, 1)
struct FLEMHeader {
    char magic[4];          // "FLEM"
    uint32_t version;       // Version (currently 1)
    uint32_t nx;            // Grid columns (X dimension)
    uint32_t ny;            // Grid rows (Y/Z dimension)
    float length_x;         // Physical length in X (m)
    float length_y;         // Physical length in Y (m)
    float h_min;            // Elevation min (m)
    float h_max;            // Elevation max (m)
    float area_min;         // Drainage area min (m^2)
    float area_max;         // Drainage area max (m^2)
    float erosion_min;      // Erosion rate min
    float erosion_max;      // Erosion rate max
    uint32_t has_water;     // 1 if water level defined
    float water_level;      // Water level threshold
    uint8_t reserved[8];    // Reserved padding (64 bytes total header)
};
#pragma pack(pop)

static_assert(sizeof(FLEMHeader) == 64, "FLEMHeader must be exactly 64 bytes");

struct FastscapeData {
    FLEMHeader header{};
    std::vector<float> elevation;     // Size: nx * ny
    std::vector<float> drainage_area; // Size: nx * ny
    std::vector<float> erosion_rate;  // Size: nx * ny
    bool is_valid = false;

    // Helpers
    float GetElevation(uint32_t x, uint32_t y) const {
        if (x >= header.nx || y >= header.ny) return 0.0f;
        return elevation[y * header.nx + x];
    }
    float GetDrainage(uint32_t x, uint32_t y) const {
        if (x >= header.nx || y >= header.ny) return 0.0f;
        return drainage_area[y * header.nx + x];
    }
    float GetErosion(uint32_t x, uint32_t y) const {
        if (x >= header.nx || y >= header.ny) return 0.0f;
        return erosion_rate[y * header.nx + x];
    }

    // Normalized drainage (log scale 0.0 to 1.0)
    float GetNormalizedDrainage(uint32_t x, uint32_t y) const;

    // Normalized elevation (0.0 to 1.0)
    float GetNormalizedElevation(uint32_t x, uint32_t y) const;

    // Normalized erosion (0.0 to 1.0)
    float GetNormalizedErosion(uint32_t x, uint32_t y) const;
};

class FastscapeLoader {
public:
    static bool LoadFromFile(const std::string& filepath, FastscapeData& out_data);
    static bool GenerateProceduralSample(uint32_t nx, uint32_t ny, FastscapeData& out_data);
};
