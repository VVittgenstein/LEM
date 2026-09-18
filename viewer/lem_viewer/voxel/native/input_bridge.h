#pragma once
#include "raylib.h"
#include <array>

// Qt forwards keys while its focus proxy owns keyboard focus. Mouse input
// continues through the original raylib window and camera controller.
inline bool host_input_active = false;
// Pointer interaction must be able to acquire focus even when both focus
// flags are false, as happens after using a Qt sidebar control.
inline bool ViewerPointerActivates(bool inside, bool pressed, bool held,
                                   float wheel, bool native_focus, bool host_focus) {
    return inside && (pressed || wheel != 0 || (held && !native_focus && !host_focus));
}
inline std::array<bool,512> host_keys{};
inline std::array<bool,512> host_pressed{};
inline std::array<bool,512> native_pressed{};
inline void CollectNativeKeys() {
    native_pressed.fill(false);
    for(int key=GetKeyPressed();key!=0;key=GetKeyPressed())
        if(key>=0 && key<int(native_pressed.size()))native_pressed[key]=true;
}
inline void HostKey(int key, bool down) {
    if(key<0 || key>=int(host_keys.size()))return;
    if(down && !host_keys[key])host_pressed[key]=true;
    host_keys[key]=down;
}
inline void HostActive(bool active) {
    host_input_active=active;
    if(!active){host_keys.fill(false);host_pressed.fill(false);}
}
inline bool ViewerKeyDown(int key) {
    return IsKeyDown(key) || (host_input_active && key>=0 && key<int(host_keys.size()) && host_keys[key]);
}
inline bool ViewerKeyPressed(int key) {
    return (key>=0 && key<int(native_pressed.size()) && native_pressed[key]) || IsKeyPressed(key) ||
           (host_input_active && key>=0 && key<int(host_pressed.size()) && host_pressed[key]);
}
