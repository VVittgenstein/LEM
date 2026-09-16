"""Lazy adapter to the real fastscape-litho model; no substitute physics."""
import importlib
import numpy as np
from .config import MATERIALS
from .geology import exposed_labels


class BackendUnavailable(RuntimeError):
    pass


def load_backend():
    try:
        xs = importlib.import_module("xsimlab")
        litho = importlib.import_module("fastscape_litho.fastscape_litho")
        importlib.import_module("fastscapelib_fortran")
        return xs, litho
    except ImportError as exc:
        raise BackendUnavailable(
            "Full execution requires fastscape-litho at SHA "
            "0ce9c7c056b197a2f558343597af7c7375ff6f20 and compatible fastscape, "
            "xarray-simlab and fastscapelib-fortran. No physics fallback is provided. "
            "Use --inputs-only for input diagnostics. Missing import: " + str(exc)
        ) from exc


def clock(duration, dt):
    times = np.arange(0.0, duration, dt)
    return np.append(times, duration)


def run(config, inputs):
    xs, litho = load_backend()
    from fastscape.processes.main import SurfaceTopography

    @xs.process
    class InitialSurface:
        initial = xs.variable(dims=("y", "x"))
        elevation = xs.foreign(SurfaceTopography, "elevation", intent="out")

        def initialize(self):
            self.elevation = self.initial.copy()

    @xs.process
    class GuardedLabel(litho.Label3D):
        def initialize(self):
            if self.origin_z != 0:
                raise ValueError("only origin_z=0 is supported")
            self.nz = self.labelmatrix.shape[2]
            self.z = np.arange(self.nz) * self.dz
            self.indices = exposed_labels(self.labelmatrix, 0.0, self.dz)

        def run_step(self):
            self.indices = exposed_labels(self.labelmatrix, self.cumulative_height, self.dz)

    model = litho.sediment_model_label3D.update_processes(
        {"label": GuardedLabel, "init_topography": InitialSurface})
    times = clock(config.duration, config.dt)
    # xsimlab saves after run_step, before finalize_step: the penultimate and
    # final cumulative snapshots can both contain the final step's erosion.
    # TotalErosion.height is the signed increment from that step (in meters).
    setup = xs.create_setup(
        model=model, clocks={"time": times, "save": times[-1:]}, master_clock="time",
        input_vars={
            "grid__shape": list(config.shape), "grid__length": list(config.length),
            "boundary__status": ["fixed_value"] * 4,
            "init_topography__initial": inputs.elevation,
            "uplift__rate": inputs.uplift, "flow__slope_exp": 1.0,
            "spl__area_exp": 0.5, "spl__slope_exp": 1.0,
            "spl__k_coef_soil": 6e-5,
            "spl__g_coef_bedrock": 0.0, "spl__g_coef_soil": 1.0,
            "label__dz": config.dz, "label__origin_z": 0.0,
            "label__labelmatrix": inputs.labels,
            "spl__Kr_lab": [m["Kr"] * config.erodibility_scale for m in MATERIALS],
            "diffusion__Kdr_lab": [m["Kdr"] * config.diffusion_scale for m in MATERIALS],
            "diffusion__Kds_lab": [m["Kds"] * config.diffusion_scale for m in MATERIALS],
        },
        output_vars={name: "save" for name in (
            "topography__elevation", "drainage__area", "erosion__cumulative_height",
            "erosion__height")},
    )
    with model:
        result = setup.xsimlab.run()
    final = result["erosion__cumulative_height"].isel(save=-1).transpose("y", "x").values
    height = result["erosion__height"].isel(save=-1).transpose("y", "x").values
    exposed = exposed_labels(inputs.labels, final, config.dz)
    fields = {
        "elevation": result["topography__elevation"].isel(save=-1).transpose("y", "x").values,
        "drainage_area": result["drainage__area"].isel(save=-1).transpose("y", "x").values,
        "erosion_rate": height / (times[-1] - times[-2]),
        "cumulative_erosion": final,
        "exposed_lithology": exposed,
    }
    for name, value in fields.items():
        if value.shape != config.shape or not np.all(np.isfinite(value)):
            raise ValueError(f"invalid backend output: {name}")
    return fields
