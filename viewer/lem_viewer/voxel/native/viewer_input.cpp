#include "viewer_input.h"
#include <fstream>
#include <filesystem>
#include <cmath>
#include <cstring>
#include <algorithm>

bool ViewerInput::Load(const std::string& filename, std::string& error) {
    std::ifstream in(std::filesystem::u8path(filename), std::ios::binary | std::ios::ate);
    if (!in) { error="Cannot open display input"; return false; }
    auto length=in.tellg(); in.seekg(0);
    if (!in.read(reinterpret_cast<char*>(&header), sizeof(header)) || std::memcmp(header.magic,"LVT1",4)) {
        error="Invalid display header"; return false;
    }
    uint64_t count=uint64_t(header.nx)*header.ny;
    if (!count || header.nx>4096 || header.ny>4096 || header.levels<2 || header.levels>4096 ||
        !std::isfinite(header.dx) || !std::isfinite(header.dy) || header.dx<=0 || header.dy<=0 ||
        !std::isfinite(header.minimum) || !std::isfinite(header.maximum) || header.maximum<header.minimum ||
        !std::isfinite(header.water) || !std::isfinite(header.exaggeration) || header.exaggeration<=0 ||
        length!=std::streamoff(sizeof(header)+count*16)) {
        error="Invalid dimensions, scale or input length"; return false;
    }
    data.header={}; data.header.nx=header.nx; data.header.ny=header.ny;
    data.header.h_min=float(header.minimum); data.header.h_max=float(header.maximum);
    data.header.has_water=header.flags&1; data.header.water_level=float(header.water);
    data.elevation.resize(count); data.drainage_area.resize(count); data.erosion_rate.resize(count); colors.resize(count);
    in.read(reinterpret_cast<char*>(data.elevation.data()),count*4);
    in.read(reinterpret_cast<char*>(data.drainage_area.data()),count*4);
    in.read(reinterpret_cast<char*>(data.erosion_rate.data()),count*4);
    in.read(reinterpret_cast<char*>(colors.data()),count*4);
    if (!in) {error="Truncated display arrays"; return false;}
    bool finite=false;
    for(float h:data.elevation) if(std::isfinite(h)) finite=true;
    if(!finite) {error="No finite elevation values"; return false;}
    float amin=0,amax=1,emin=0,emax=1;
    for(float a:data.drainage_area) if(std::isfinite(a)){amin=std::min(amin,a);amax=std::max(amax,a);}
    for(float e:data.erosion_rate) if(std::isfinite(e)){emin=std::min(emin,e);emax=std::max(emax,e);}
    data.header.area_min=amin;data.header.area_max=amax;data.header.erosion_min=emin;data.header.erosion_max=emax;
    data.is_valid=true; return true;
}
