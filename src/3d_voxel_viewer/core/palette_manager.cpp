#include "palette_manager.h"
#include <fstream>
#include <sstream>
#include <iostream>
#include <algorithm>
#include <cmath>

PaletteManager::PaletteManager() {
    SetupDefaults();
}

void PaletteManager::SetupDefaults() {
    // Biome defaults
    biome.bedrock = {45, 42, 42, 255};
    biome.stone   = {110, 105, 100, 255};
    biome.dirt    = {120, 90, 55, 255};
    biome.grass   = {78, 136, 56, 255};
    biome.forest  = {47, 90, 40, 255};
    biome.snow    = {242, 245, 248, 255};
    biome.sand    = {217, 190, 139, 255};
    biome.water   = {29, 91, 153, 220};

    // Elevation gradient stops (0.0 to 1.0)
    elevation.stops = {
        {0.00f, {45, 107, 53, 255}},    // Lowland valley
        {0.20f, {90, 150, 67, 255}},    // Plains
        {0.40f, {140, 168, 88, 255}},   // Lower slopes
        {0.60f, {196, 176, 123, 255}},  // Mid rocky slopes
        {0.80f, {140, 130, 122, 255}},  // High crags
        {1.00f, {245, 248, 252, 255}}   // Snow peak
    };

    // Hydrology gradient (logarithmic drainage area)
    hydrology.stops = {
        {0.00f, {27, 38, 59, 255}},     // Ridge / divide (navy dark)
        {0.25f, {34, 87, 122, 255}},    // Hillside flow
        {0.50f, {0, 150, 199, 255}},    // Minor stream
        {0.75f, {72, 202, 228, 255}},   // Major river channel
        {1.00f, {202, 240, 248, 255}}   // Main river artery (glowing cyan/white)
    };

    // Erosion gradient
    erosion.stops = {
        {0.00f, {59, 130, 246, 255}},   // Deposition (blue)
        {0.25f, {16, 185, 129, 255}},   // Stable / neutral (green)
        {0.50f, {234, 179, 8, 255}},    // Moderate erosion (yellow)
        {0.75f, {249, 115, 22, 255}},   // High incision (orange)
        {1.00f, {239, 68, 68, 255}}     // Severe incision (red)
    };
}

Color PaletteManager::LerpColor(Color c1, Color c2, float t) {
    t = std::clamp(t, 0.0f, 1.0f);
    return Color{
        static_cast<unsigned char>(c1.r + (c2.r - c1.r) * t),
        static_cast<unsigned char>(c1.g + (c2.g - c1.g) * t),
        static_cast<unsigned char>(c1.b + (c2.b - c1.b) * t),
        static_cast<unsigned char>(c1.a + (c2.a - c1.a) * t)
    };
}

static Color SampleGradient(const std::vector<std::pair<float, Color>>& stops, float value) {
    if (stops.empty()) return WHITE;
    if (value <= stops.front().first) return stops.front().second;
    if (value >= stops.back().first) return stops.back().second;

    for (size_t i = 0; i < stops.size() - 1; ++i) {
        if (value >= stops[i].first && value <= stops[i + 1].first) {
            float range = stops[i + 1].first - stops[i].first;
            float t = (range > 0.0001f) ? (value - stops[i].first) / range : 0.0f;
            return PaletteManager::LerpColor(stops[i].second, stops[i + 1].second, t);
        }
    }
    return stops.back().second;
}

Color PaletteManager::ParseHex(const std::string& hex_str, uint8_t default_alpha) {
    std::string s = hex_str;
    if (!s.empty() && s[0] == '#') s = s.substr(1);
    uint32_t val = 0;
    std::stringstream ss;
    ss << std::hex << s;
    ss >> val;

    if (s.length() == 6) {
        uint8_t r = (val >> 16) & 0xFF;
        uint8_t g = (val >> 8) & 0xFF;
        uint8_t b = val & 0xFF;
        return Color{r, g, b, default_alpha};
    } else if (s.length() == 8) {
        uint8_t r = (val >> 24) & 0xFF;
        uint8_t g = (val >> 16) & 0xFF;
        uint8_t b = (val >> 8) & 0xFF;
        uint8_t a = val & 0xFF;
        return Color{r, g, b, a};
    }
    return WHITE;
}

bool PaletteManager::LoadFromIni(const std::string& filepath) {
    std::ifstream file(filepath);
    if (!file.is_open()) {
        std::cerr << "[PaletteManager] Could not open palette file: " << filepath
                  << " (using defaults)" << std::endl;
        return false;
    }

    std::string line, current_section;
    while (std::getline(file, line)) {
        // Strip comments and whitespace
        size_t comment_pos = line.find_first_of("#;");
        if (comment_pos != std::string::npos) line = line.substr(0, comment_pos);

        line.erase(0, line.find_first_not_of(" \t\r\n"));
        line.erase(line.find_last_not_of(" \t\r\n") + 1);
        if (line.empty()) continue;

        if (line.front() == '[' && line.back() == ']') {
            current_section = line.substr(1, line.length() - 2);
            continue;
        }

        size_t eq_pos = line.find('=');
        if (eq_pos == std::string::npos) continue;

        std::string key = line.substr(0, eq_pos);
        std::string val = line.substr(eq_pos + 1);
        key.erase(0, key.find_first_not_of(" \t"));
        key.erase(key.find_last_not_of(" \t") + 1);
        val.erase(0, val.find_first_not_of(" \t"));
        val.erase(val.find_last_not_of(" \t") + 1);

        if (current_section == "general") {
            if (key == "default_scheme") current_scheme = static_cast<ColorSchemeType>(std::stoi(val));
            else if (key == "ao_darkness") ao_darkness = std::stof(val);
            else if (key == "voxel_height_steps") voxel_height_steps = std::stoi(val);
            else if (key == "water_level_voxels") water_level_voxels = std::stoi(val);
        } else if (current_section == "biome") {
            Color c = ParseHex(val);
            if (key == "bedrock") biome.bedrock = c;
            else if (key == "stone") biome.stone = c;
            else if (key == "dirt") biome.dirt = c;
            else if (key == "grass") biome.grass = c;
            else if (key == "forest") biome.forest = c;
            else if (key == "snow") biome.snow = c;
            else if (key == "sand") biome.sand = c;
            else if (key == "water") biome.water = c;
        }
    }
    std::cout << "[PaletteManager] Loaded palette configuration from " << filepath << std::endl;
    return true;
}

void PaletteManager::CycleScheme() {
    current_scheme = static_cast<ColorSchemeType>((current_scheme + 1) % SCHEME_COUNT);
}

void PaletteManager::SetScheme(ColorSchemeType scheme) {
    current_scheme = static_cast<ColorSchemeType>(scheme % SCHEME_COUNT);
}

const char* PaletteManager::GetCurrentSchemeName() const {
    switch (current_scheme) {
        case SCHEME_BIOME: return "1. Biome & Geology";
        case SCHEME_ELEVATION: return "2. Hypsometric Elevation";
        case SCHEME_HYDROLOGY: return "3. Hydrology & Runoff Heatmap";
        case SCHEME_EROSION: return "4. Geomorphic Erosion Intensity";
        default: return "Unknown";
    }
}

Color PaletteManager::GetFaceColor(uint8_t voxel_type,
                                   const ColumnAttributes& col,
                                   int normal_axis,
                                   int normal_sign,
                                   int ao_level) const {
    Color base_color = WHITE;

    if (voxel_type == VOXEL_WATER) {
        base_color = biome.water;
    } else {
        switch (current_scheme) {
            case SCHEME_BIOME: {
                switch (voxel_type) {
                    case VOXEL_BEDROCK: base_color = biome.bedrock; break;
                    case VOXEL_STONE: base_color = biome.stone; break;
                    case VOXEL_DIRT: base_color = biome.dirt; break;
                    case VOXEL_GRASS: {
                        // Vary grass slightly based on drainage (river valley lushness)
                        if (col.norm_drainage > 0.4f) {
                            base_color = LerpColor(biome.grass, biome.forest, (col.norm_drainage - 0.4f) * 1.5f);
                        } else {
                            base_color = biome.grass;
                        }
                        break;
                    }
                    case VOXEL_SNOW: base_color = biome.snow; break;
                    case VOXEL_SAND: base_color = biome.sand; break;
                    default: base_color = biome.stone; break;
                }
                break;
            }
            case SCHEME_ELEVATION: {
                base_color = SampleGradient(elevation.stops, col.norm_elevation);
                break;
            }
            case SCHEME_HYDROLOGY: {
                base_color = SampleGradient(hydrology.stops, col.norm_drainage);
                break;
            }
            case SCHEME_EROSION: {
                base_color = SampleGradient(erosion.stops, col.norm_erosion);
                break;
            }
            default:
                base_color = biome.stone;
                break;
        }
    }

    // Directional normal lighting factor
    float normal_shade = 1.0f;
    if (normal_axis == 1) { // Y axis
        normal_shade = (normal_sign > 0) ? 1.0f : 0.50f;
    } else if (normal_axis == 0) { // X axis
        normal_shade = 0.84f;
    } else { // Z axis
        normal_shade = 0.74f;
    }

    // Vertex Ambient Occlusion (AO) attenuation
    // ao_level in [0, 3], where 3 is full ambient, 0 is full corner occlusion
    ao_level = std::clamp(ao_level, 0, 3);
    float ao_factors[4] = {
        1.0f - ao_darkness * 1.8f,
        1.0f - ao_darkness * 1.2f,
        1.0f - ao_darkness * 0.6f,
        1.0f
    };
    float ao_mult = std::max(0.15f, ao_factors[ao_level]);

    float final_mult = normal_shade * ao_mult;

    return Color{
        static_cast<unsigned char>(std::clamp(base_color.r * final_mult, 0.0f, 255.0f)),
        static_cast<unsigned char>(std::clamp(base_color.g * final_mult, 0.0f, 255.0f)),
        static_cast<unsigned char>(std::clamp(base_color.b * final_mult, 0.0f, 255.0f)),
        base_color.a
    };
}
