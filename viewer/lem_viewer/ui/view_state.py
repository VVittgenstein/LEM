"""Independent display settings for each of the two viewport slots."""
from dataclasses import dataclass

@dataclass
class ViewState:
    mode: str = "surface_3d"
    channel: str = ""
    palette: str = "fem"
    levels: int = 12
    vertical_exaggeration: float = 1.0
    max_display_size: int = 512
    height_levels: int = 36
    material: bool = False
    water_auto: bool = True
    water_metres: float = 0.0
    camera_mode: int = 0
    show_grid: bool = False
    show_hud: bool = False
    show_profiler: bool = False
    culling: bool = True
    fps_limit: int = 60

    def display_options(self) -> dict:
        return {"palette": self.palette, "levels": self.levels,
                "vertical_exaggeration": self.vertical_exaggeration or None,
                "max_display_size": self.max_display_size, "height_levels": self.height_levels,
                "material": self.material, "water_override": None if self.water_auto else self.water_metres}

    def native_options(self) -> dict:
        return {name: getattr(self, name) for name in (
            "camera_mode", "show_grid", "show_hud", "show_profiler", "culling", "fps_limit")}
