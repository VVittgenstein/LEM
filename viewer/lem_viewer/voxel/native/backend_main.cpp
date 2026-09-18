// Qt-managed renderer, adapted from J31415's standalone main.cpp.
#include "raylib.h"
#include "raymath.h"
#include "rlgl.h"
#include "core/voxel_grid.h"
#include "core/voxel_mesher.h"
#include "core/palette_manager.h"
#include "core/camera_controller.h"
#include "core/hud.h"
#include "viewer_input.h"
#include "input_bridge.h"
#include <iostream>
#include <iomanip>
#include <sstream>
#include <string>
#include <memory>
#include <algorithm>
#include <cmath>
#include <stdexcept>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOGDI
#define NOUSER
#include <windows.h>
#else
#include <unistd.h>
#include <sys/select.h>
#endif

static std::string Escape(const std::string& s){std::string r;for(char c:s){if(c=='"'||c=='\\')r+='\\';if(c=='\n'||c=='\r')r+=' ';else r+=c;}return r;}
static void Event(const std::string& json){std::cout<<"\nLEM_EVENT "<<json<<std::endl;}
static bool ReadCommands(std::string& buffer){
    char bytes[4096];
#ifdef _WIN32
    auto input=GetStdHandle(STD_INPUT_HANDLE);DWORD count=0,read=0;
    if(!PeekNamedPipe(input,nullptr,0,nullptr,&count,nullptr)) return GetLastError()!=ERROR_BROKEN_PIPE;
    while(count){if(!ReadFile(input,bytes,std::min<DWORD>(count,sizeof(bytes)),&read,nullptr)||!read)return false;buffer.append(bytes,read);if(!PeekNamedPipe(input,nullptr,0,nullptr,&count,nullptr))break;}
#else
    fd_set set;FD_ZERO(&set);FD_SET(STDIN_FILENO,&set);timeval timeout{};
    while(select(STDIN_FILENO+1,&set,nullptr,nullptr,&timeout)>0){auto n=read(STDIN_FILENO,bytes,sizeof(bytes));if(n<=0)return false;buffer.append(bytes,n);FD_ZERO(&set);FD_SET(STDIN_FILENO,&set);timeout={};}
#endif
    return true;
}

int main(int argc,char** argv){
    bool verify=argc==3&&std::string(argv[1])=="--verify";
    SetTraceLogLevel(LOG_WARNING);
    SetConfigFlags(FLAG_WINDOW_RESIZABLE|FLAG_WINDOW_HIDDEN|FLAG_MSAA_4X_HINT|FLAG_WINDOW_ALWAYS_RUN);
    InitWindow(640,480,"LEM Voxel View");SetExitKey(KEY_NULL);SetTargetFPS(60);
#ifdef _WIN32
    // This window handles camera keys, not text. Disable IME composition only
    // for its HWND so letter keys reach raylib under non-Latin input methods.
    if(auto imm=LoadLibraryW(L"imm32.dll")){
        using Associate=HANDLE (WINAPI *)(HWND,HANDLE);
        if(auto associate=reinterpret_cast<Associate>(GetProcAddress(imm,"ImmAssociateContext")))
            associate(reinterpret_cast<HWND>(GetWindowHandle()),nullptr);
        FreeLibrary(imm);
    }
#endif
    if(!IsWindowReady()){Event("{\"event\":\"error\",\"message\":\"OpenGL window initialization failed\"}");return 2;}
    std::unique_ptr<VoxelGrid> grid;
    std::unique_ptr<VoxelMesher> mesher;
    PaletteManager palette;CameraController camera;HUD hud;FrameProfile profile{};
    hud.show_hud=false;hud.show_profiler=false;
    profile.frustum_culling_enabled=true;profile.fps_mode=1;
    bool running=true,show_grid=false,need_capture=false;
    std::string capture,buffer;double last_state=0;int revision=0;
    auto load=[&](const std::string& path,int request,bool reset){
        try{
            ViewerInput input;std::string error;if(!input.Load(path,error))throw std::runtime_error(error);
            auto next=std::make_unique<VoxelGrid>();auto next_mesh=std::make_unique<VoxelMesher>();
            next->ConfigurePhysical(input.data,input.header.dx,input.header.dy,int(input.header.levels),input.header.exaggeration);
            next->QuantizeFromFastscape(input.data,int(input.header.levels),next->water_layer);
            for(size_t i=0;i<input.colors.size();++i)next->column_attrs[i].display_color=input.colors[i];
            auto next_palette=palette;next_palette.SetScheme((input.header.flags&2)?SCHEME_BIOME:SCHEME_CHANNEL);
            if(!next_mesh->BuildMesh(*next,next_palette))throw std::runtime_error("No drawable voxel mesh");
            bool first=!grid;double old_unit=grid?grid->scene_unit_m:next->scene_unit_m;
            auto old_camera=camera;
            grid=std::move(next);mesher=std::move(next_mesh);palette=std::move(next_palette);revision=request;
            camera.SetGrid(grid.get());
            {
                float peak=grid->WorldHeight(float(grid->max_ground_y+1));
                float center_x=(grid->size_x/2)*grid->cell_x,center_z=(grid->size_z/2)*grid->cell_z;
                float center=grid->GroundHeightWorldAt(center_x,center_z);
                if(!std::isfinite(center))center=grid->WorldHeight(grid->center_ground_y+1);
                float extent=std::max(grid->size_x*grid->cell_x,grid->size_z*grid->cell_z);
                camera.Setup(Vector3{center_x,center,center_z},extent,peak,center,grid.get());
            }
            if(!first&&!reset){
                float factor=float(old_unit/grid->scene_unit_m);
                camera.camera.position=Vector3Scale(old_camera.camera.position,factor);
                camera.camera.target=Vector3Scale(old_camera.camera.target,factor);
                camera.camera.fovy=old_camera.camera.fovy;
                camera.orbit_target=Vector3Scale(old_camera.orbit_target,factor);
                camera.orbit_distance=old_camera.orbit_distance*factor;
                camera.orbit_yaw=old_camera.orbit_yaw;camera.orbit_pitch=old_camera.orbit_pitch;
                camera.fly_yaw=old_camera.fly_yaw;camera.fly_pitch=old_camera.fly_pitch;
                camera.fly_speed=old_camera.fly_speed*factor;camera.mode=old_camera.mode;
            }
            std::ostringstream result;result<<std::setprecision(9)<<"{\"event\":\"loaded\",\"revision\":"<<revision
                <<",\"quads\":"<<mesher->stats.optimized_quads<<",\"levels\":"<<input.header.levels
                <<",\"minimum_m\":"<<input.header.minimum<<",\"maximum_m\":"<<input.header.maximum
                <<",\"layer_m\":"<<(input.header.maximum-input.header.minimum)/(input.header.levels-1)
                <<",\"scene_unit_m\":"<<grid->scene_unit_m<<",\"top_min_scene\":"<<grid->WorldHeight(1)
                <<",\"top_max_scene\":"<<grid->WorldHeight(float(input.header.levels))<<"}";Event(result.str());
        }catch(const std::bad_alloc&){Event("{\"event\":\"error\",\"revision\":"+std::to_string(request)+",\"message\":\"Not enough memory to build the voxel view. Reduce height levels or display size.\"}");}
        catch(const std::exception& e){Event("{\"event\":\"error\",\"revision\":"+std::to_string(request)+",\"message\":\""+Escape(e.what())+"\"}");}
    };
    if(verify){load(argv[2],1,true);if(mesher){mesher->Unload();mesher.reset();}CloseWindow();return grid?0:1;}
    Event("{\"event\":\"ready\",\"handle\":"+std::to_string(reinterpret_cast<uintptr_t>(GetWindowHandle()))+"}");
    while(running&&!WindowShouldClose()){
        if(!ReadCommands(buffer))break;
        size_t end;
        while((end=buffer.find('\n'))!=std::string::npos){
            std::string line=buffer.substr(0,end);buffer.erase(0,end+1);std::istringstream cmd(line);std::string name;cmd>>name;
            if(name=="QUIT"){running=false;break;}
            if(name=="ACTIVE"){int value=0;cmd>>value;HostActive(value!=0);}
            else if(name=="KEY"){int key=0,down=0;cmd>>key>>down;HostKey(key,down!=0);}
            if(name=="LOAD"){std::string path;int id=0,reset=0;cmd>>std::quoted(path)>>id>>reset;load(path,id,reset!=0);}
            else if(name=="CAMERA"){int mode=0;cmd>>mode;camera.SetMode(mode?CAM_FLYCAM:CAM_ORBIT);}
            else if(name=="RESET")camera.Reset();
            else if(name=="FOCUS")SetWindowFocused();
            else if(name=="GRID"){int v=0;cmd>>v;show_grid=v!=0;}
            else if(name=="HUD"){int v=0;cmd>>v;hud.show_hud=v!=0;}
            else if(name=="PROFILER"){int v=0;cmd>>v;hud.show_profiler=v!=0;if(v)hud.show_hud=true;}
            else if(name=="CULL"){int v=0;cmd>>v;profile.frustum_culling_enabled=v!=0;}
            else if(name=="FPS"){int v=60;cmd>>v;v=(v==0||v==60||v==144)?v:60;SetTargetFPS(v);profile.fps_mode=v==0?0:v==60?1:2;}
            else if(name=="CAPTURE"){cmd>>std::quoted(capture);need_capture=true;}
            else if(name=="PALETTE"){
                std::string path;cmd>>std::quoted(path);
                try {
                    auto next=palette;
                    if(!next.LoadFromIni(path))throw std::runtime_error("Cannot open material palette");
                    if(!std::isfinite(next.ao_darkness)||next.ao_darkness<0||next.ao_darkness>1)
                        throw std::runtime_error("Palette AO darkness must be between zero and one");
                    next.SetScheme(palette.current_scheme);
                    if(mesher&&grid){auto next_mesh=std::make_unique<VoxelMesher>();
                        if(!next_mesh->BuildMesh(*grid,next))throw std::runtime_error("Cannot rebuild palette mesh");
                        mesher=std::move(next_mesh);}
                    palette=std::move(next);
                }catch(const std::exception& e){Event("{\"event\":\"error\",\"message\":\""+Escape(e.what())+"\"}");}
            }
            else if(name=="POSE"){
                int mode=0;cmd>>mode>>camera.camera.position.x>>camera.camera.position.y>>camera.camera.position.z
                    >>camera.camera.target.x>>camera.camera.target.y>>camera.camera.target.z
                    >>camera.orbit_target.x>>camera.orbit_target.y>>camera.orbit_target.z
                    >>camera.orbit_distance>>camera.orbit_yaw>>camera.orbit_pitch>>camera.fly_yaw>>camera.fly_pitch>>camera.fly_speed;
                float fovy=45.f;
                if(cmd>>fovy && std::isfinite(fovy))camera.camera.fovy=std::clamp(fovy,1.f,90.f);
                else camera.camera.fovy=45.f;
                camera.mode=mode?CAM_FLYCAM:CAM_ORBIT;
            }
        }
        if(!running)break;
        TimeProbe frame;frame.Start();
        TimeProbe input_probe;input_probe.Start();
        CollectNativeKeys();
        const bool mouse_pressed=IsMouseButtonPressed(MOUSE_BUTTON_LEFT)||
            IsMouseButtonPressed(MOUSE_BUTTON_RIGHT)||IsMouseButtonPressed(MOUSE_BUTTON_MIDDLE);
        const bool mouse_held=IsMouseButtonDown(MOUSE_BUTTON_LEFT)||
            IsMouseButtonDown(MOUSE_BUTTON_RIGHT)||IsMouseButtonDown(MOUSE_BUTTON_MIDDLE);
        if(ViewerPointerActivates(IsCursorOnScreen(),mouse_pressed,mouse_held,
                                 GetMouseWheelMove(),IsWindowFocused(),host_input_active)){
            // Focus recovery is outside the focused-input branch. A click,
            // drag or wheel operation on this window activates it immediately.
            HostActive(true);
            SetWindowFocused();
            Event("{\"event\":\"activate\"}");
        }
        if(host_input_active){
            if(ViewerKeyPressed(KEY_M))camera.ToggleMode();
            if(ViewerKeyPressed(KEY_R))camera.Reset();
            if(ViewerKeyPressed(KEY_G))show_grid=!show_grid;
            if(ViewerKeyPressed(KEY_H))hud.show_hud=!hud.show_hud;
            if(ViewerKeyPressed(KEY_F3)){hud.show_profiler=!hud.show_profiler;if(hud.show_profiler)hud.show_hud=true;}
            if(ViewerKeyPressed(KEY_F))profile.frustum_culling_enabled=!profile.frustum_culling_enabled;
            if(ViewerKeyPressed(KEY_V)){profile.fps_mode=(profile.fps_mode+1)%3;SetTargetFPS(profile.fps_mode==0?0:profile.fps_mode==1?60:144);}
            if(ViewerKeyPressed(KEY_F11))Event("{\"event\":\"fullscreen\"}");
            if(ViewerKeyPressed(KEY_C))Event("{\"event\":\"color\",\"scheme\":\"cycle\"}");
            if(ViewerKeyPressed(KEY_ONE))Event("{\"event\":\"color\",\"scheme\":\"material\"}");
            if(ViewerKeyPressed(KEY_TWO))Event("{\"event\":\"color\",\"scheme\":\"elevation\"}");
            if(ViewerKeyPressed(KEY_THREE))Event("{\"event\":\"color\",\"scheme\":\"drainage_area\"}");
            if(ViewerKeyPressed(KEY_FOUR))Event("{\"event\":\"color\",\"scheme\":\"erosion_rate\"}");
            if(ViewerKeyPressed(KEY_L))Event("{\"event\":\"open\"}");
            if(ViewerKeyPressed(KEY_P))Event("{\"event\":\"palette\"}");
            if(IsFileDropped()){auto paths=LoadDroppedFiles();if(paths.count)Event("{\"event\":\"drop\",\"path\":\""+Escape(paths.paths[0])+"\"}");UnloadDroppedFiles(paths);}
        }
        profile.t_input_us=input_probe.StopUs();
        TimeProbe camera_probe;camera_probe.Start();
        if(host_input_active)camera.Update(GetFrameTime());
        host_pressed.fill(false);
        profile.t_camera_us=camera_probe.StopUs();
        BeginDrawing();ClearBackground(Color{26,30,36,255});
        if(mesher){
            float aspect=float(GetScreenWidth())/std::max(1,GetScreenHeight());
            profile.total_submeshes=mesher->stats.submesh_count;profile.visible_submeshes=profile.culled_submeshes=0;
            BeginMode3D(camera.camera);camera.ApplyCustomProjection(aspect);
            TimeProbe draw;draw.Start();mesher->Draw(Vector3{},1,&camera.camera,aspect,&profile,camera.far_plane_distance);profile.t_render3d_us=draw.StopUs();
            if(show_grid)DrawGrid(32,std::max(1.f,camera.terrain_max_dim/32));EndMode3D();
            TimeProbe overlay;overlay.Start();hud.Draw(camera,palette,*mesher,*grid,profile,"Terrain",GetScreenWidth(),GetScreenHeight());profile.t_hud_us=overlay.StopUs();
        }else DrawText("Loading terrain...",20,20,20,LIGHTGRAY);
        TimeProbe present;present.Start();EndDrawing();profile.t_present_us=present.StopUs();
        profile.t_frame_total_ms=frame.StopMs();profile.fps=float(GetFPS());
        if(need_capture){
            // The embedded HWND is already sized in physical pixels by Qt.
            // LoadImageFromScreen adds monitor DPI again on this Windows path.
            Image frame_image{};frame_image.width=GetRenderWidth();frame_image.height=GetRenderHeight();
            frame_image.mipmaps=1;frame_image.format=PIXELFORMAT_UNCOMPRESSED_R8G8B8A8;
            frame_image.data=rlReadScreenPixels(frame_image.width,frame_image.height);
            ExportImage(frame_image,capture.c_str());UnloadImage(frame_image);need_capture=false;
            Event("{\"event\":\"captured\"}");
        }
        if(grid&&GetTime()-last_state>.2){
            last_state=GetTime();std::ostringstream pose;pose<<std::setprecision(8)<<int(camera.mode)<<' '
                <<camera.camera.position.x<<' '<<camera.camera.position.y<<' '<<camera.camera.position.z<<' '
                <<camera.camera.target.x<<' '<<camera.camera.target.y<<' '<<camera.camera.target.z<<' '
                <<camera.orbit_target.x<<' '<<camera.orbit_target.y<<' '<<camera.orbit_target.z<<' '
                <<camera.orbit_distance<<' '<<camera.orbit_yaw<<' '<<camera.orbit_pitch<<' '<<camera.fly_yaw<<' '<<camera.fly_pitch<<' '<<camera.fly_speed<<' '<<camera.camera.fovy;
            Event("{\"event\":\"state\",\"pose\":\""+pose.str()+"\",\"camera\":"+std::to_string(int(camera.mode))+
                ",\"grid\":"+(show_grid?"true":"false")+",\"hud\":"+(hud.show_hud?"true":"false")+
                ",\"profiler\":"+(hud.show_profiler?"true":"false")+",\"culling\":"+(profile.frustum_culling_enabled?"true":"false")+
                ",\"fps_mode\":"+std::to_string(profile.fps_mode)+",\"fps\":"+std::to_string(GetFPS())+
                ",\"scene_unit_m\":"+std::to_string(grid->scene_unit_m)+"}");
        }
    }
    if(mesher){mesher->Unload();mesher.reset();}CloseWindow();return 0;
}
