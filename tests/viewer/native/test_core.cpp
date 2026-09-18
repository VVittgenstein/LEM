#include "core/voxel_grid.h"
#include "core/palette_manager.h"
#include "viewer_input.h"
#include "input_bridge.h"
#include "core/camera_controller.h"
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <filesystem>
#include <fstream>
#include <climits>

void expect(bool value,const char* message){if(!value)throw std::runtime_error(message);}
int main(int argc,char** argv){try{
    expect(ViewerPointerActivates(true,true,false,0,false,false),"defocused viewport must reacquire on click");
    expect(ViewerPointerActivates(true,false,true,0,false,false),"defocused viewport must reacquire on drag");
    expect(ViewerPointerActivates(true,false,false,1,false,false),"defocused viewport must reacquire on wheel");
    expect(!ViewerPointerActivates(false,true,true,1,false,false),"pointer outside viewport must not acquire focus");
    expect(!ViewerPointerActivates(true,false,false,0,false,false),"hover must not steal sidebar focus");
    expect(!ViewerPointerActivates(true,false,true,0,true,true),"active drag must not repeatedly change focus");
    HostActive(true);HostKey(KEY_M,true);HostKey(KEY_M,false);
    expect(ViewerKeyPressed(KEY_M),"short host key press must survive release within one frame");
    HostKey(KEY_W,true);expect(ViewerKeyDown(KEY_W),"held movement key");
    HostActive(false);expect(!ViewerKeyDown(KEY_W),"focus loss must clear held keys");
    CameraController camera;
    camera.orbit_distance=5.f;
    camera.Zoom(100);
    expect(std::abs(camera.orbit_distance-.05f)<1e-6,"zoom must allow voxel detail below the old five-cell limit");
    camera.Zoom(-100);
    expect(camera.orbit_distance>0 && std::isfinite(camera.orbit_distance),"fast wheel input must retain a positive distance");
    camera.orbit_distance=10.f;camera.Zoom(2);camera.Zoom(-2);
    expect(std::abs(camera.orbit_distance-10.f)<1e-4,"opposite wheel steps restore zoom");
    camera.mode=CAM_FLYCAM;
    auto initial_position=camera.camera.position;float initial_speed=camera.fly_speed;
    camera.Zoom(8);
    expect(camera.camera.fovy<45.f,"fly wheel must magnify the view");
    expect(camera.fly_speed==initial_speed && camera.camera.position.x==initial_position.x &&
           camera.camera.position.y==initial_position.y && camera.camera.position.z==initial_position.z,
           "fly zoom preserves position and speed");
    camera.Zoom(-8);expect(std::abs(camera.camera.fovy-45.f)<1e-4,"fly wheel zooms back out");
    camera.Zoom(100);camera.Reset();expect(camera.camera.fovy==45.f,"reset restores normal field of view");
    FastscapeData data;data.is_valid=true;data.header.nx=3;data.header.ny=2;
    data.header.h_min=-100;data.header.h_max=3400;data.header.has_water=1;data.header.water_level=0;
    data.elevation={-100,1250,3400,400,1800,std::numeric_limits<float>::quiet_NaN()};
    data.drainage_area.assign(6,0);data.erosion_rate.assign(6,0);
    for(int levels:{2,36,72,256}){
        VoxelGrid grid;grid.ConfigurePhysical(data,1000,2000,levels,1);
        grid.QuantizeFromFastscape(data,levels,grid.water_layer);
        expect(std::abs(grid.cell_x-0.5f)<1e-6,"horizontal x spacing");
        expect(std::abs(grid.cell_z-1.f)<1e-6,"horizontal z spacing");
        expect(std::abs(grid.WorldHeight(1)+0.05f)<1e-6,"minimum height must be level invariant");
        expect(std::abs(grid.WorldHeight(0)+0.55f)<1e-6,"base height must be level invariant");
        expect(std::abs(grid.WorldHeight(float(levels))-1.7f)<1e-6,"maximum height must be level invariant");
        expect(std::abs(grid.GroundHeightWorldAt(1,0)-1.7f)<1e-6,"collision coordinates");
        expect(grid.GetColumn(2,1).ground_height==-1,"invalid height must remain a hole");
        expect(std::abs(grid.WorldHeight(float(grid.water_layer+1),true))<1e-6,"water uses physical datum");
    }
    data.header.h_max=data.header.h_min=-2000;data.elevation.assign(6,-2000);
    VoxelGrid flat;flat.ConfigurePhysical(data,1000,1000,72,1);flat.QuantizeFromFastscape(data,72,flat.water_layer);
    expect(std::abs(flat.GroundHeightWorldAt(0,0)+2)<1e-5,"flat physical elevation");
    expect(flat.CountWaterVoxels()>0,"flat submerged terrain");
    expect(VoxelGrid::CheckedVoxelCount(500,3615,500)==903750000ULL,"above 512 MiB is allowed");
    VoxelGrid wide;wide.size_x=4096;wide.size_y=4100;wide.size_z=4096;
    expect(wide.GetIndex(4095,4099,4095)==4096ULL*4100*4096-1,"voxel index remains correct above 32 bits");
    bool rejected=false;try{VoxelGrid::CheckedVoxelCount(INT_MAX,INT_MAX,INT_MAX);}catch(const std::exception&){rejected=true;}
    expect(rejected,"allocation arithmetic overflow must be rejected");
    if(argc>1 && std::string(argv[1])=="--large-allocation"){
        auto input_path=std::filesystem::current_path()/"large-viewer-input.bin";
        ViewerHeader header{{'L','V','T','1'},500,500,3611,0,1000,1000,0,1,0,1};
        std::vector<uint32_t> input_arrays(500*500*4,0);
        {std::ofstream out(input_path,std::ios::binary);
            out.write(reinterpret_cast<const char*>(&header),sizeof(header));
            out.write(reinterpret_cast<const char*>(input_arrays.data()),input_arrays.size()*4);}
        ViewerInput input;std::string error;
        expect(input.Load(input_path.u8string(),error),error.c_str());
        std::filesystem::remove(input_path);
        VoxelGrid large;large.Allocate(500,3615,500);
        large.SetVoxel(499,3614,499,VOXEL_STONE);
        expect(large.voxels.size()==903750000ULL && large.GetVoxel(499,3614,499)==VOXEL_STONE,
               "large allocation preserves last-voxel access");
        std::cout<<"Large allocation passed: "<<large.voxels.size()<<" bytes\n";
    }
    expect(PaletteManager::ParseHex("#123456").r==0x12,"hex colors");
    auto palette_path=std::filesystem::current_path()/std::filesystem::u8path(u8"palette-\u6d4b\u8bd5.ini");
    {std::ofstream out(palette_path);out<<"[biome]\ngrass = #12ab34\n";}
    PaletteManager loaded_palette;
    expect(loaded_palette.LoadFromIni(palette_path.u8string()),"Unicode palette path");
    expect(loaded_palette.biome.grass.r==0x12 && loaded_palette.biome.grass.g==0xab,"INI hex color preservation");
    std::filesystem::remove(palette_path);
    std::cout<<"Physical scale, level invariance, water, holes, allocation and palette checks passed\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
