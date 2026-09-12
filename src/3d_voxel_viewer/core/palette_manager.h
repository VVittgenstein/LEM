#pragma once

#include "raylib.h"
#include "voxel_grid.h"
#include <string>
#include <vector>
#include <array>

enum ColorSchemeType {
    SCHEME_BIOME = 0,
    SCHEME_ELEVATION = 1,
    SCHEME_HYDROLOGY = 2,
    SCHEME_EROSION = 3,
    SCHEME_COUNT
};

struct BiomeColors {
    Color bedrock{50, 45, 45, 255};
    Color stone{115, 110, 105, 255};
    Color dirt{130, 95, 60, 255};
    Color grass{75, 140, 55, 255};
    Color forest{45, 95, 40, 255};
    Color snow{245, 250, 255, 255};
    Color sand{220, 195, 140, 255};
    Color water{30, 100, 175, 210};
};

struct ElevationPalette {
    std::vector<std::pair<float, Color>> stops; // (altitude_fraction, color)
};

struct HydrologyPalette {
    std::vector<std::pair<float, Color>> stops; // (drainage_log_fraction, color)
};

struct ErosionPalette {
    std::vector<std::pair<float, Color>> stops; // (erosion_fraction, color)
};

class PaletteManager {
public:
    PaletteManager();

    ColorSchemeType current_scheme = SCHEME_BIOME;
    float ao_darkness = 0.28f;
    int voxel_height_steps = 36;
    int water_level_voxels = 2;

    BiomeColors biome;
    ElevationPalette elevation;
    HydrologyPalette hydrology;
    ErosionPalette erosion;

    bool LoadFromIni(const std::string& filepath);
    void SetupDefaults();
    void CycleScheme();
    void SetScheme(ColorSchemeType scheme);

    const char* GetCurrentSchemeName() const;

    // Evaluates final vertex color including face normal lighting and Ambient Occlusion
    Color GetFaceColor(uint8_t voxel_type,
                       const ColumnAttributes& col,
                       int normal_axis, // 0: X, 1: Y, 2: Z
                       int normal_sign, // +1 or -1
                       int ao_level) const;

    static Color LerpColor(Color c1, Color c2, float t);
    static Color ParseHex(const std::string& hex_str, uint8_t default_alpha = 255);
};
