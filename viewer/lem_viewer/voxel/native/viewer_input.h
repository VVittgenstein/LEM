#pragma once
#include "core/fastscape_loader.h"
#include <string>
#pragma pack(push, 1)
struct ViewerHeader {
    char magic[4];
    uint32_t nx, ny, levels, flags;
    double dx, dy, minimum, maximum, water, exaggeration;
};
#pragma pack(pop)
static_assert(sizeof(ViewerHeader) == 68);
struct ViewerInput {
    ViewerHeader header{};
    FastscapeData data;
    std::vector<uint32_t> colors;
    bool Load(const std::string& filename, std::string& error);
};
