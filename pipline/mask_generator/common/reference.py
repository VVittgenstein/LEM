"""Read-only GSHHG inputs, continuous shape alignment and reference statistics."""
from dataclasses import dataclass
from pathlib import Path
import struct

import numpy as np
from scipy.spatial.distance import cdist

from .config import (GSHHG, PIXELS_PER_UNIT, POPULATION, REFERENCE_MASKS,
                     REFERENCE_TABLE, TEMPLATE_SIZE, VERSION)
from .io import array_sha256, file_sha256, read_csv, read_json, utc_now, write_csv, write_json
from .metrics import shape_metrics


@dataclass
class ReferenceBundle:
    template: np.ndarray
    model: dict
    manifest: dict
    directory: Path


def polygon_parts(geometry):
    if geometry.geom_type == "Polygon":
        yield geometry
    elif hasattr(geometry, "geoms"):
        for child in geometry.geoms:
            yield from polygon_parts(child)


def footprint(geometry):
    import shapely
    from shapely.geometry import Polygon
    repaired = shapely.make_valid(geometry) if not geometry.is_valid else geometry
    parts = [Polygon(p.exterior) for p in polygon_parts(repaired) if p.area > 0]
    if not parts:
        raise ValueError("reference has no positive-area polygon")
    return shapely.union_all(parts)


def geometry_diameter(geometry) -> float:
    points = np.asarray(geometry.convex_hull.exterior.coords)[:-1]
    maximum = 0.0
    for start in range(0, len(points), 256):
        maximum = max(maximum, float(cdist(points[start:start + 256], points, "sqeuclidean").max()))
    if maximum <= 0:
        raise ValueError("reference has zero extent")
    return float(np.sqrt(maximum))


def align_geometry(geometry):
    """Exact polygon area centroid/moments; principal axis sign uses the third moment.

    Symmetric fallback: non-negative local x component (then non-negative y).
    Near-isotropic shapes use local x. These are deterministic geometric conventions.
    """
    from shapely.affinity import affine_transform

    geometry = footprint(geometry)
    center = np.asarray(geometry.centroid.coords[0], dtype=float)
    rings = []
    area = 0.0
    covariance_integral = np.zeros((2, 2))
    for part in polygon_parts(geometry):
        ring = np.asarray(part.exterior.coords, dtype=float) - center
        p, q = ring[:-1], ring[1:]
        cross = p[:, 0] * q[:, 1] - q[:, 0] * p[:, 1]
        sign = 1.0 if cross.sum() >= 0 else -1.0
        cross *= sign
        area += float(cross.sum() / 2)
        xx = np.sum(cross * (p[:, 0] ** 2 + p[:, 0] * q[:, 0] + q[:, 0] ** 2)) / 12
        yy = np.sum(cross * (p[:, 1] ** 2 + p[:, 1] * q[:, 1] + q[:, 1] ** 2)) / 12
        xy = np.sum(cross * (2*p[:, 0]*p[:, 1] + p[:, 0]*q[:, 1] + q[:, 0]*p[:, 1] + 2*q[:, 0]*q[:, 1])) / 24
        covariance_integral += [[xx, xy], [xy, yy]]
        rings.append((p, q, cross))
    covariance = covariance_integral / area
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    if eigenvalues[0] <= 0:
        raise ValueError("degenerate area covariance")
    isotropic = bool((eigenvalues[1] - eigenvalues[0]) / eigenvalues[1] < 1e-10)
    vector = np.array([1.0, 0.0]) if isotropic else eigenvectors[:, 1].copy()
    third = 0.0
    for p, q, cross in rings:
        u, v = p @ vector, q @ vector
        third += float(np.sum(cross * (u**3 + u*u*v + u*v*v + v**3)) / 20)
    third /= area
    tolerance = 1e-10 * float(eigenvalues[1] ** 1.5)
    if abs(third) > tolerance:
        sign_rule = "positive third central area moment along major axis"
        if third < 0:
            vector *= -1
            third *= -1
    else:
        sign_rule = "symmetric fallback: positive local x, then positive local y"
        if vector[0] < -1e-12 or (abs(vector[0]) <= 1e-12 and vector[1] < 0):
            vector *= -1
    diameter = geometry_diameter(geometry)
    rotation = np.array([[vector[0], vector[1]], [-vector[1], vector[0]]])
    matrix = rotation / diameter
    offset = -matrix @ center
    aligned = affine_transform(geometry, [*matrix[0], *matrix[1], *offset])
    # Shapely order is [a,b,d,e,xoff,yoff], matching row-major matrix above.
    info = {"native_area_km2": float(geometry.area), "native_centroid_km": center.tolist(),
            "native_diameter_km": diameter, "native_axis_ratio": float(np.sqrt(eigenvalues[1]/eigenvalues[0])),
            "alignment_angle_deg": float(np.degrees(np.arctan2(vector[1], vector[0]))),
            "axis_sign_rule": sign_rule, "near_isotropic": isotropic,
            "third_central_moment_km3": third, "scale_to_relative_unit": 1.0 / diameter,
            "aligned_area_relative2": float(aligned.area), "aligned_bounds": list(aligned.bounds),
            "aligned_centroid": list(aligned.centroid.coords[0]), "affine_matrix": matrix.tolist(),
            "affine_offset": offset.tolist()}
    return aligned, info


def rasterize_aligned(geometry, size: int = TEMPLATE_SIZE) -> np.ndarray:
    import shapely
    coords = (np.arange(size, dtype=float) + 0.5 - size / 2) / PIXELS_PER_UNIT
    out = np.zeros((size, size), dtype=bool)
    bounds = geometry.bounds
    lo = -size / (2 * PIXELS_PER_UNIT)
    hi = size / (2 * PIXELS_PER_UNIT)
    if min(bounds[:2]) <= lo or max(bounds[2:]) >= hi:
        raise ValueError("aligned reference does not fit the intermediate canvas")
    shapely.prepare(geometry)
    for row in range(0, size, 128):
        out[row:row+128] = shapely.contains_xy(geometry, coords[None, :], coords[row:row+128, None])
    return out


class GSHHGReader:
    """GSHHG 2.3.7 big-endian binary reader, selecting the requested level-1 IDs."""
    def __init__(self, path: Path, wanted: set[int]):
        self.path = path
        self.index = {}
        with path.open("rb") as stream:
            while len(self.index) < len(wanted):
                header = stream.read(44)
                if not header:
                    break
                if len(header) != 44:
                    raise ValueError("truncated GSHHG header")
                gid, n, flag, *_ = struct.unpack(">11i", header)
                if n < 0:
                    raise ValueError("invalid GSHHG coordinate count")
                if gid in wanted:
                    if flag & 255 != 1:
                        raise ValueError(f"GSHHG {gid} is not a level-1 shoreline")
                    self.index[gid] = (stream.tell(), n)
                stream.seek(n * 8, 1)
        missing = wanted - set(self.index)
        if missing:
            raise ValueError(f"GSHHG members missing: {sorted(missing)}")

    def geometry(self, gid: int, longitude: float, latitude: float):
        from pyproj import CRS, Transformer
        from shapely.geometry import Polygon
        from shapely.ops import transform

        offset, n = self.index[gid]
        with self.path.open("rb") as stream:
            stream.seek(offset)
            raw = stream.read(n * 8)
        if len(raw) != n * 8:
            raise ValueError(f"truncated GSHHG coordinates for {gid}")
        coords = np.frombuffer(raw, dtype=">i4").astype(float).reshape(n, 2) / 1e6
        coords[:, 0] = np.rad2deg(np.unwrap(np.deg2rad(coords[:, 0])))
        coords[:, 0] += 360 * round((longitude - coords[:, 0].mean()) / 360)
        geo = footprint(Polygon(coords))
        crs = CRS.from_proj4(f"+proj=laea +lat_0={latitude} +lon_0={longitude} +datum=WGS84 +units=km +no_defs")
        projection = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        return footprint(transform(projection.transform, geo))


def fit_reference_model(rows: list[dict]) -> dict:
    area = np.asarray([r["area_km2"] for r in rows])
    design = np.column_stack([np.ones(len(area)), np.log(area)])
    result = {"member_ids": [r["id"] for r in rows], "n": len(rows),
              "area_range_km2": [float(area.min()), float(area.max())], "member_weight": "equal",
              "form": "log(metric) = intercept + slope * log(area_km2) + residual", "metrics": {}}
    for key in ("axis_ratio", "shoreline_development"):
        response = np.log([r[key] for r in rows])
        coef = np.linalg.lstsq(design, response, rcond=None)[0]
        residual = response - design @ coef
        iqr = float(np.quantile(residual, 0.75) - np.quantile(residual, 0.25))
        result["metrics"][key] = {"intercept": float(coef[0]), "slope": float(coef[1]),
                                  "residuals": residual.tolist(), "residual_iqr": iqr,
                                  "loss_normalizer": max(0.1, iqr), "reference_values": np.exp(response).tolist()}
    return result


def expected_log_metric(model: dict, key: str, area):
    entry = model["metrics"][key]
    return entry["intercept"] + entry["slope"] * np.log(area)


def prepare_reference(directory: Path, log=print) -> ReferenceBundle:
    from .render import reference_atlas, scalar_png, save_mask_png

    members = read_csv(POPULATION)
    if len(members) != 34 or len({m["id"] for m in members}) != 34:
        raise ValueError("the selected population must contain exactly 34 unique IDs")
    source_rows = {r["id"]: r for r in read_csv(REFERENCE_TABLE)}
    inputs = [POPULATION, REFERENCE_TABLE, GSHHG]
    for member in members:
        if member["id"] not in source_rows:
            raise ValueError(f"missing reference row {member['id']}")
        inputs.append(REFERENCE_MASKS / (member["id"] + ".npz"))
    missing = [str(p) for p in inputs if not p.is_file()]
    if missing:
        raise FileNotFoundError("reference inputs missing: " + "; ".join(missing))
    identities = [{"path": str(path), "bytes": path.stat().st_size, "sha256": file_sha256(path)} for path in inputs]
    reader = GSHHGReader(GSHHG, {int(source_rows[m["id"]]["gshhg_id"]) for m in members})
    directory.mkdir(parents=True, exist_ok=True)
    count = np.zeros((TEMPLATE_SIZE, TEMPLATE_SIZE), dtype=np.uint8)
    stats, alignment, native_panels, aligned_panels = [], [], [], []
    for index, member in enumerate(members):
        rid = member["id"]
        gid = int(source_rows[rid]["gshhg_id"])
        geometry = reader.geometry(gid, float(member["longitude"]), float(member["latitude"]))
        aligned, info = align_geometry(geometry)
        image = rasterize_aligned(aligned)
        count += image.astype(np.uint8)
        with np.load(REFERENCE_MASKS / f"{rid}.npz", allow_pickle=False) as data:
            native = np.asarray(data["focal"], dtype=bool)
            if float(data["dx_km"]) != 1.0:
                raise ValueError(f"reference {rid} has a different cell size")
        row = {"id": rid, "name": member["name"], **shape_metrics(native)}
        stats.append(row)
        info.update({"id": rid, "gshhg_id": gid, "name": member["name"], "weight": 1/34,
                     "aligned_cells": int(image.sum()), "aligned_mask_sha256": array_sha256(image)})
        alignment.append(info)
        member_dir = directory / "aligned" / rid
        member_dir.mkdir(parents=True, exist_ok=True)
        np.save(member_dir / "mask.npy", image)
        save_mask_png(member_dir / "mask.png", image)
        write_json(member_dir / "alignment.json", info)
        native_panels.append((rid, native))
        aligned_panels.append((rid, image))
        log(f"reference {index+1}/34 {rid}", flush=True)
    template = count.astype(np.float64) / 34.0
    np.save(directory / "coverage_count.npy", count)
    np.save(directory / "coverage.npy", template)
    scalar_png(directory / "coverage.png", template, "envelope")
    scalar_png(directory / "center_crop.png", template[262:762, 262:762], "envelope")
    reference_atlas(directory / "reference_shapes.png", native_panels, "Reference footprints at native 1 km spacing")
    reference_atlas(directory / "aligned_shapes.png", aligned_panels, "Equal-span, centroid and major-axis alignment")
    model = fit_reference_model(stats)
    write_json(directory / "shape_model.json", model)
    write_csv(directory / "reference_metrics.csv", stats)
    write_csv(directory / "members.csv", members)
    write_json(directory / "alignment.json", alignment)
    manifest = {"created_utc": utc_now(), "version": VERSION, "member_ids": [m["id"] for m in members],
                "input_files": identities, "source": "GSHHG 2.3.7 full-resolution level-1 shorelines; D native 1 km focal masks",
                "template_shape": [TEMPLATE_SIZE, TEMPLATE_SIZE], "relative_longest_span": 1.0,
                "pixels_per_relative_unit": PIXELS_PER_UNIT, "coverage_weight": "1/34 per member",
                "coverage_array_sha256": array_sha256(template),
                "evidence_state": "本项目借鉴或合成改造；相对尺寸、对齐和叠加规则为本轮方案",
                "note": "参考图形的相对归一化不规定其在最终掩膜中的面积占比。"}
    write_json(directory / "manifest.json", manifest)
    return ReferenceBundle(template, model, manifest, directory)


def load_reference(directory: Path) -> ReferenceBundle:
    manifest = read_json(directory / "manifest.json")
    template = np.load(directory / "coverage.npy", allow_pickle=False)
    if array_sha256(template) != manifest["coverage_array_sha256"]:
        raise ValueError("reference template hash mismatch")
    for source in manifest["input_files"]:
        if file_sha256(Path(source["path"])) != source["sha256"]:
            raise ValueError(f"reference input changed: {source['path']}; rerun prepare and calibrate")
    return ReferenceBundle(template, read_json(directory / "shape_model.json"), manifest, directory)
