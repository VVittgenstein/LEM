import numpy as np
from scipy.ndimage import label, maximum_filter, minimum_filter


def terrain_derivatives(elevation, dx):
    """Calculate review channels in SI units from a two-dimensional surface."""
    surface = np.asarray(elevation, dtype=float)
    if surface.ndim != 2 or min(surface.shape) < 3 or not np.all(np.isfinite(surface)):
        raise ValueError("elevation must be a finite two-dimensional array")
    if not np.isfinite(dx) or dx <= 0:
        raise ValueError("dx must be positive and finite")
    dy, derivative_x = np.gradient(surface, dx, dx)
    slope = np.hypot(derivative_x, dy)
    normal_x, normal_y, normal_z = -derivative_x, -dy, np.ones(surface.shape)
    norm = np.sqrt(normal_x**2 + normal_y**2 + normal_z**2)
    # Northwest illumination with a 35 degree source altitude.
    altitude, azimuth = np.deg2rad(35.0), np.deg2rad(315.0)
    light = (np.cos(altitude) * np.sin(azimuth),
             np.cos(altitude) * np.cos(azimuth), np.sin(altitude))
    hillshade = np.clip((normal_x * light[0] + normal_y * light[1] + normal_z * light[2]) / norm,
                        0.0, 1.0)
    window = max(3, int(round(5000.0 / dx)))
    if window % 2 == 0:
        window += 1
    window = min(window, min(surface.shape) if min(surface.shape) % 2 else min(surface.shape) - 1)
    radius = window // 2
    yy, xx = np.ogrid[-radius:radius + 1, -radius:radius + 1]
    footprint = xx * xx + yy * yy <= radius * radius
    local_relief = maximum_filter(surface, footprint=footprint, mode="nearest") - minimum_filter(
        surface, footprint=footprint, mode="nearest")
    return {"slope": slope, "hillshade": hillshade, "local_relief": local_relief}


def coastline_mask(elevation, water_level=0.0):
    """Return land cells adjacent to sea using four-neighbour connectivity."""
    surface = np.asarray(elevation, dtype=float)
    if surface.ndim != 2 or not np.all(np.isfinite(surface)) or not np.isfinite(water_level):
        raise ValueError("surface and water level must be finite")
    land = surface > water_level
    coast = np.zeros_like(land)
    coast[1:, :] |= land[1:, :] & ~land[:-1, :]
    coast[:-1, :] |= land[:-1, :] & ~land[1:, :]
    coast[:, 1:] |= land[:, 1:] & ~land[:, :-1]
    coast[:, :-1] |= land[:, :-1] & ~land[:, 1:]
    return coast


def _summary(array):
    values = np.asarray(array, dtype=float)
    return {
        "min": float(values.min()),
        "p05": float(np.percentile(values, 5)),
        "median": float(np.median(values)),
        "p95": float(np.percentile(values, 95)),
        "max": float(values.max()),
        "mean": float(values.mean()),
    }


def input_diagnostics(config, inputs):
    land = np.asarray(inputs.elevation) > 0.0
    components, count = label(land, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]))
    component_sizes = np.bincount(components.ravel())[1:]
    neighbour_jumps = np.concatenate((np.abs(np.diff(inputs.uplift, axis=0)).ravel(),
                                      np.abs(np.diff(inputs.uplift, axis=1)).ravel()))
    represented, represented_counts = np.unique(inputs.landform[land], return_counts=True)
    represented = [int(value) for value in represented]
    represented_fractions = {
        str(int(value)): float(count / land.sum())
        for value, count in zip(represented, represented_counts)
    }
    available_fraction = float(
        max(config.ny - 2 * config.ocean_buffer_cells, 0)
        * max(config.nx - 2 * config.ocean_buffer_cells, 0)
        / (config.nx * config.ny)
    )
    land_elevation = np.asarray(inputs.elevation, dtype=float)[land]
    return {
        "land_fraction": float(land.mean()),
        "target_land_fraction": float(config.target_land_fraction),
        "target_land_fraction_reached": bool(
            abs(float(land.mean()) - config.target_land_fraction) <= 1 / land.size
        ),
        "maximum_land_fraction_with_buffer": available_fraction,
        "ocean_buffer_cells": int(config.ocean_buffer_cells),
        "ocean_on_north_edge": bool(np.all(~land[-1, :])),
        "ocean_on_south_edge": bool(np.all(~land[0, :])),
        "ocean_on_east_edge": bool(np.all(~land[:, -1])),
        "ocean_on_west_edge": bool(np.all(~land[:, 0])),
        "land_component_count_4": int(count),
        "main_land_component_fraction": (float(component_sizes.max() / land.sum())
                                         if component_sizes.size else 0.0),
        "planned_landforms": list(inputs.planned_landforms),
        "planned_landform_count": len(inputs.planned_landforms),
        "represented_landform_ids": represented,
        "represented_landform_count": len(represented),
        "represented_landform_land_fractions": represented_fractions,
        "uplift_m_per_yr": _summary(inputs.uplift),
        "ridge_system_count": int(inputs.ridge_system_count),
        "ridge_field": _summary(inputs.ridge_field),
        "ridge_support_cell_fraction_above_0_35": float(np.mean(inputs.ridge_field > 0.35)),
        "uplift_max_neighbor_jump_m_per_yr": float(neighbour_jumps.max()),
        "uplift_p95_neighbor_jump_m_per_yr": float(np.percentile(neighbour_jumps, 95)),
        "initial_elevation_m": _summary(inputs.elevation),
        "initial_elevation_range_m": float(np.ptp(inputs.elevation)),
        "initial_land_elevation_m": _summary(land_elevation),
        "surface_lithology_ids": sorted(int(value) for value in np.unique(inputs.labels[..., 0])),
    }


def output_diagnostics(config, fields):
    elevation = np.asarray(fields["elevation"], dtype=float)
    derivatives = terrain_derivatives(elevation, config.dx)
    drainage = np.asarray(fields["drainage_area"], dtype=float)
    positive = drainage[drainage > 0]
    threshold = float(np.percentile(positive, 95)) if positive.size else 0.0
    coast = coastline_mask(elevation)
    land = elevation > 0.0
    components, count = label(land, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]))
    component_sizes = np.bincount(components.ravel())[1:]
    land_slope = derivatives["slope"][land]
    land_slope_angle = np.degrees(np.arctan(land_slope))
    land_relief = derivatives["local_relief"][land]
    return {
        "land_fraction": float(land.mean()),
        "land_fraction_in_requested_range": bool(0.5 <= land.mean() <= 0.75),
        "land_component_count_4": int(count),
        "main_land_component_fraction": (float(component_sizes.max() / land.sum())
                                         if component_sizes.size else 0.0),
        "ocean_on_north_edge": bool(np.all(~land[-1, :])),
        "ocean_on_south_edge": bool(np.all(~land[0, :])),
        "ocean_on_east_edge": bool(np.all(~land[:, -1])),
        "ocean_on_west_edge": bool(np.all(~land[:, 0])),
        "elevation_m": _summary(elevation),
        "elevation_range_m": float(np.ptp(elevation)),
        "elevation_range_in_requested_4000_to_6000_m": bool(4000 <= np.ptp(elevation) <= 6000),
        "land_elevation_m": _summary(elevation[land]) if np.any(land) else None,
        "slope_m_per_m": _summary(derivatives["slope"]),
        "land_slope_m_per_m": _summary(land_slope) if land_slope.size else None,
        "land_slope_angle_degrees": _summary(land_slope_angle) if land_slope.size else None,
        "land_slope_above_45deg_fraction": float(np.mean(land_slope > 1.0)) if land_slope.size else 0.0,
        "local_relief_m": _summary(derivatives["local_relief"]),
        "land_local_relief_m": _summary(land_relief) if land_relief.size else None,
        "drainage_area_m2": _summary(drainage),
        "river_display_threshold_m2": threshold,
        "river_display_cell_fraction": float(np.mean(drainage >= threshold)) if threshold > 0 else 0.0,
        "coastline_cell_count": int(coast.sum()),
        "erosion_rate_m_per_yr": _summary(fields["erosion_rate"]),
        "cumulative_erosion_m": _summary(fields["cumulative_erosion"]),
        "exposed_lithology_ids": sorted(int(value) for value in np.unique(fields["exposed_lithology"])),
    }
