"""Freeze EarthByte M2 PlateFrame grids and calculate interval-specific data."""
import io
import urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from scipy.io import netcdf_file
import context as c

COLLECTION = "https://www.earthbyte.org/webdav/ftp/Data_Collections/Muller_etal_2018_GR/"
BASE = COLLECTION + "DynamicTopoData/M2/PlateFrame/"
FILES = (0, 9, 19, 29, 39, 49)
KM_DEG = 111.195


def freeze_sources(out):
    folder = out / "source"
    folder.mkdir(exist_ok=True)
    urls = [(f"M2.{age}.Ma.nc", BASE + f"M2.{age}.Ma.nc") for age in FILES]
    urls += [("README.txt", COLLECTION + "README.txt"), ("License.txt", COLLECTION + "License.txt")]
    prior = c.read_json(folder / "sources.json") if (folder / "sources.json").exists() else None
    expected = {r["file"]: r["sha256"] for r in prior["files"]} if prior else {}

    def get(item):
        name, url = item
        dest = folder / name
        if not dest.exists():
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read()
            if name.endswith(".nc") and data[:3] != b"CDF":
                raise ValueError(f"Unexpected source format: {name}")
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(dest)
        digest = c.file_sha256(dest)
        if name in expected and expected[name] != digest:
            raise ValueError(f"Frozen source hash changed: {name}")
        return {"file": name, "url": url, "bytes": dest.stat().st_size, "sha256": digest}
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(get, urls))
    payload = {"retrieved_utc": prior["retrieved_utc"] if prior else c.utc_now(),
               "model": "M2", "frame": "PlateFrame", "files": rows,
               "paper": "Muller et al. 2018, DOI 10.1016/j.gr.2017.04.028",
               "kind": "mantle-convection model prediction of dynamic topography",
               "grid_note": "z has no explicit units attribute; metres follow the publication and selected input definition"}
    c.write_json(folder / "sources.json", payload)
    return payload


def load_window(out):
    source = freeze_sources(out)
    grids, metadata = {}, {}
    axes = None
    for age in FILES:
        path = out / "source" / f"M2.{age}.Ma.nc"
        with netcdf_file(io.BytesIO(path.read_bytes()), "r", mmap=False) as f:
            lon = f.variables["lon"][:].copy()
            lat = f.variables["lat"][:].copy()
            z = f.variables["z"][:].copy().astype(float)
            metadata[str(age)] = {k: str(v) for k, v in f._attributes.items()}
        if axes is None:
            axes = lon, lat
        elif not np.array_equal(lon, axes[0]) or not np.array_equal(lat, axes[1]):
            raise ValueError("M2 time slices have different coordinate grids")
        if z.shape != (len(lat), len(lon)) or not np.all(np.diff(lon) > 0) or not np.all(np.diff(lat) > 0):
            raise ValueError("Invalid grid coordinate contract")
        grids[age] = z
    x_km = (lon - 73.) * KM_DEG * np.cos(np.deg2rad(41.))
    y_km = (lat - 41.) * KM_DEG
    ix, iy = np.flatnonzero(abs(x_km) <= 250.), np.flatnonzero(abs(y_km) <= 250.)
    # Preserve the native 99 nodes; do not count a dense interpolation as extra observations.
    values = {age: z[np.ix_(iy, ix)] for age, z in grids.items()}
    if not all(np.isfinite(z).all() for z in values.values()):
        raise ValueError("Missing M2 values in the selected window")
    z48 = .9 * values[49] + .1 * values[39]
    history = np.stack([z48 if age == 48 else values[int(age)] for age in c.AGES_MA])
    duration = np.diff(c.ELAPSED_MYR)
    delta = np.diff(history, axis=0)
    rates = delta / duration[:, None, None]  # m/Myr
    weights = np.broadcast_to(np.cos(np.deg2rad(lat[iy]))[:, None], rates.shape[1:]).copy()
    cumulative = history - history[0]
    bounds = [73.-250/(KM_DEG*np.cos(np.deg2rad(41.))),
              73.+250/(KM_DEG*np.cos(np.deg2rad(41.))), 41.-250/KM_DEG, 41.+250/KM_DEG]
    rows = []
    for i, rate in enumerate(rates):
        mean = float(np.sum(rate * weights) / weights.sum())
        std = float(np.sqrt(np.sum(weights * (rate - mean)**2) / weights.sum()))
        rows.append({"interval": i + 1, "start_elapsed_Myr": c.ELAPSED_MYR[i],
                     "end_elapsed_Myr": c.ELAPSED_MYR[i+1], "duration_Myr": float(duration[i]),
                     "old_age_Ma_BP": c.AGES_MA[i], "young_age_Ma_BP": c.AGES_MA[i+1],
                     "rate_mean_m_per_Myr": mean, "rate_std_m_per_Myr": std,
                     "rate_min_m_per_Myr": float(rate.min()), "rate_max_m_per_Myr": float(rate.max()),
                     "net_mean_m": mean * duration[i], "net_std_m": std * duration[i],
                     "native_nodes": int(rate.size)})
    np.savez_compressed(out / "reference_window.npz", longitude=lon[ix], latitude=lat[iy],
                        x_km=x_km[ix], y_km=y_km[iy], weights=weights,
                        ages_Ma_BP=c.AGES_MA, elapsed_Myr=c.ELAPSED_MYR,
                        elevation_m=history, cumulative_m=cumulative,
                        interval_net_m=delta, rates_m_per_Myr=rates)
    detail = {"center_lon_lat": [73., 41.], "nominal_window_km": [500., 500.],
              "requested_bounds_lon_lat": bounds, "native_lon": lon[ix].tolist(),
              "native_lat": lat[iy].tolist(), "native_shape": list(rate.shape),
              "native_spacing_deg": [float(lon[1]-lon[0]), float(lat[1]-lat[0])],
              "time_48Ma": "0.9 * z(49 Ma BP) + 0.1 * z(39 Ma BP)",
              "difference_direction": "z(younger) - z(older); positive is upward",
              "spatial_weights": "cos(latitude), native nodes only, population standard deviation",
              "projection": "local equirectangular distances at 41 deg N, 111.195 km/deg",
              "final_cumulative_m": {"min": float(cumulative[-1].min()), "max": float(cumulative[-1].max()),
                    "weighted_mean": float(np.sum(cumulative[-1]*weights)/weights.sum())},
              "source": source, "grid_metadata": metadata, "intervals": rows}
    c.write_json(out / "reference.json", detail)
    c.write_csv(out / "reference_intervals.csv", rows)
    return detail
