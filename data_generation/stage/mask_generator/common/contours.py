"""Exact cell-edge polygons, retaining every component and every interior ring."""
import numpy as np


def mask_geometry(mask: np.ndarray, dx: float = 1.0):
    import shapely

    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2 or dx <= 0:
        raise ValueError("expected a two-dimensional mask and a positive cell size")
    # Rectangles of occupied row runs have exactly the same area as the cells.
    # Their union retains diagonal point contacts and avoids marching-square
    # ambiguity or corner chamfers. No morphology is applied to the mask.
    changes = np.diff(np.pad(mask, ((0, 0), (1, 1))).astype(np.int8), axis=1)
    sy, sx = np.nonzero(changes == 1)
    ey, ex = np.nonzero(changes == -1)
    if not len(sx):
        return shapely.GeometryCollection()
    if not np.array_equal(sy, ey):
        raise RuntimeError("row runs are not paired")
    rectangles = shapely.box(sx*dx, sy*dx, ex*dx, (sy+1)*dx)
    return shapely.union_all(rectangles)


def extract_contours(mask: np.ndarray, dx: float = 1.0) -> dict:
    from shapely.geometry.polygon import orient
    from .reference import polygon_parts

    geometry = mask_geometry(mask, dx)
    polygons = sorted(polygon_parts(geometry), key=lambda p: (-p.area, p.bounds))
    components = []
    for index, polygon in enumerate(polygons, 1):
        polygon = orient(polygon, sign=1.0)
        holes = sorted(polygon.interiors, key=lambda r: tuple(r.bounds))
        components.append({"id": index, "area_km2": float(polygon.area),
                           "outer": [list(p) for p in polygon.exterior.coords],
                           "holes": [[list(p) for p in ring.coords] for ring in holes]})
    return {"coordinate_system": "local Cartesian kilometres; x right, y up; origin at lower-left domain corner",
            "array_convention": "mask[row,column]; centre x=(column+0.5)*dx, y=(row+0.5)*dx",
            "geometry": "exact occupied cell edges; exterior counter-clockwise, interiors clockwise",
            "cell_km": dx, "shape": list(mask.shape), "area_km2": float(geometry.area),
            "valid": bool(geometry.is_valid), "component_count": len(components),
            "interior_ring_count": sum(len(c["holes"]) for c in components), "components": components}


def geometry_from_contours(contours: dict):
    import shapely
    from shapely.geometry import Polygon
    return shapely.union_all([Polygon(c["outer"], holes=c["holes"]) for c in contours["components"]])


def rasterize_contours(contours: dict) -> np.ndarray:
    import shapely
    geometry = geometry_from_contours(contours)
    shapely.prepare(geometry)
    height, width = contours["shape"]
    dx = contours["cell_km"]
    x = (np.arange(width) + 0.5) * dx
    y = (np.arange(height) + 0.5) * dx
    return shapely.contains_xy(geometry, x[None, :], y[:, None])
