import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import numpy as np
from . import UPSTREAM_SHA, __version__
from .config import Config, LANDFORMS, MATERIALS, PRESETS
from .geology import generate
from .backend import BackendUnavailable, load_backend, run, clock
from .diagnostics import input_diagnostics, output_diagnostics
from .export import write_flem
from .plotting import plot_inputs, plot_outputs, plot_terrain_3d


def parser():
    p = argparse.ArgumentParser(description="Experimental fastscape-litho 3D lithology pipeline (m, yr).")
    for name in ("nx", "ny", "seed", "lithology_seed_offset"):
        p.add_argument("--" + name.replace("_", "-"), dest=name, type=int,
                       default=getattr(Config(), name))
    for name in ("dx", "depth", "dz", "duration", "dt", "target_land_fraction",
                 "ocean_buffer_fraction", "uplift_scale", "initial_relief_scale",
                 "erodibility_scale", "diffusion_scale"):
        p.add_argument("--" + name.replace("_", "-"), dest=name, type=float,
                       default=getattr(Config(), name))
    p.add_argument("--preset", choices=PRESETS, default=Config().preset)
    p.add_argument("--output", type=Path, default=Path("output/lem_litho_pipeline"))
    p.add_argument("--inputs-only", action="store_true", help="Generate geology and diagnostics without importing the LEM backend")
    p.add_argument("--no-plots", action="store_true")
    return p


def execute(c, output, inputs_only=False, plots=True):
    if not inputs_only:
        load_backend()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    versions = {"python": platform.python_version(), "pipeline": __version__}
    for package in ("numpy", "scipy", "matplotlib", "fastscape-litho", "fastscape",
                    "xarray-simlab", "fastscapelib-fortran"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    manifest = {
        "schema_version": 2,
        "status": "started", "config": c.to_dict(), "versions": versions,
        "required_fastscape_litho_sha": UPSTREAM_SHA,
        "upstream_revision_verification": "User must verify installed checkout; package version cannot establish Git SHA",
        "materials": MATERIALS,
        "landform_ids": dict(enumerate(LANDFORMS)),
        "province_ids": dict(enumerate(PRESETS[:4])),
        "geometry": {"volume_axes": ["y", "x", "z"], "volume_dtype": "uint8",
                     "nz": c.nz, "node_spans_yx_m": c.length,
                     "water_level_m": 0.0,
                     "depth_coordinate": "k*dz downward from initial local surface, co-uplifting columns",
                     "lookup": "bedrock voxel intercept: positive net cumulative erosion uses ceil(erosion/dz); finite negative values clamp to depth index 0; nonfinite values and positive depth exhaustion error"},
        "units": {"length": "m", "time": "yr", "uplift": "m/yr", "erosion_rate": "m/yr",
                  "drainage_area": "m^2", "slope": "m/m", "local_relief": "m",
                  "Kr": "yr^-1 (m=0.5, n=1)", "Kdr": "m^2/yr", "Kds": "m^2/yr"},
        "process_parameters": {"area_exp": 0.5, "slope_exp": 1.0, "flow_slope_exp": 1.0,
                               "Ksoil": 6e-5, "G_bedrock": 0.0, "G_soil": 1.0,
                               "uplift_scale": c.uplift_scale,
                               "initial_relief_scale": c.initial_relief_scale,
                               "erodibility_scale": c.erodibility_scale,
                               "diffusion_scale": c.diffusion_scale,
                               "lithology_seed_offset": c.lithology_seed_offset,
                               "effective_Kr": [m["Kr"] * c.erodibility_scale for m in MATERIALS],
                               "effective_Kdr": [m["Kdr"] * c.diffusion_scale for m in MATERIALS],
                               "effective_Kds": [m["Kds"] * c.diffusion_scale for m in MATERIALS],
                               "boundary_EWNS": ["fixed_value"] * 4},
        "assumptions": ["Provisional geological environments; no ecological biomes or calibration",
                        "Initial column-relative layering, no dynamic faulting, intrusion or marine model",
                        "Landform IDs record dominant members of smoothly blended planning weights",
                        "Signed net erosion includes deposition and is retained in outputs",
                        "At finite negative net erosion, the voxel intercept is original top bedrock (depth index 0)",
                        "Final exposed lithology denotes a bedrock voxel intercept; sediment cover is not relabeled",
                        "Drainage is the backend last routing state before final surface update"],
    }
    manifest_path = output / "manifest.json"
    try:
        inputs = generate(c, output / "lithology_volume.npy")
        np.savez(output / "inputs.npz", elevation=inputs.elevation, uplift=inputs.uplift,
                 province=inputs.province, landform=inputs.landform,
                 landform_weights=inputs.landform_weights, land_mask=inputs.land_mask,
                 ridge_field=inputs.ridge_field,
                 surface_lithology=inputs.labels[:, :, 0])
        manifest["input_diagnostics"] = input_diagnostics(c, inputs)
        if plots:
            plot_inputs(output / "inputs.png", c, inputs)
            plot_terrain_3d(output / "inputs_3d.png", inputs.elevation, c.dx,
                            "Initial terrain surface")
        if not inputs_only:
            fields = run(c, inputs)
            np.savez(output / "surface_fields.npz", **fields)
            write_flem(output / "surface.flem", fields["elevation"], fields["drainage_area"],
                       fields["erosion_rate"], c.dx, water_level=0.0)
            manifest["output_diagnostics"] = output_diagnostics(c, fields)
            if plots:
                plot_outputs(output / "surface.png", fields, c.dx)
                plot_terrain_3d(output / "surface_3d.png", fields["elevation"], c.dx,
                                "Evolved terrain surface")
            times = clock(c.duration, c.dt)
            manifest["erosion_interval_yr"] = times[-2:].tolist()
        manifest["status"] = "inputs_only" if inputs_only else "completed"
        manifest["sha256"] = {}
        for path in sorted(output.iterdir()):
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            manifest["sha256"][path.name] = digest.hexdigest()
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        with manifest_path.open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2, allow_nan=False)
    return output


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        c = Config(**{key: getattr(args, key) for key in Config.__dataclass_fields__})
        output = execute(c, args.output, args.inputs_only, not args.no_plots)
    except (ValueError, FileExistsError, BackendUnavailable) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {'input diagnostics' if args.inputs_only else 'model outputs'} to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
