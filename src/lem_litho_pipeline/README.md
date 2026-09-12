# Experimental LEM + 3D lithology pipeline

Independent experimental code. It does not change the current strategy, existing pipelines, or `src/3d_voxel_viewer`. Geological “biomes” here mean provisional geological environments. There is no ecological biome model, calibration, validation against observations, or training-data acceptance claim.

## Run

From the repository root (Python must see the `src` directory):

```sh
PYTHONPATH=src python -m lem_litho_pipeline --help
PYTHONPATH=src python -m lem_litho_pipeline --inputs-only --nx 64 --ny 48 --output output/litho-input-check
PYTHONPATH=src python -m lem_litho_pipeline --output output/litho-run
```

PowerShell: set `$env:PYTHONPATH = "src"` before the Python command. Every execution requires a new output directory. Existing directories and FLEM files are never overwritten. Failed executions retain a `failed` manifest and partial artifacts. Dependency failure is checked before creating the directory.

Defaults: 1024 × 1024 nodes, 100 m isotropic spacing, 6000 m column depth, 50 m depth spacing, seed 21, 100000 yr duration, 1000 yr step, `mosaic` preset. Node spans are 102300 m in each horizontal direction. A shortened last step is supported. All physical lengths use meters and time uses years. Use `--nx`, `--ny`, `--dx`, `--depth`, `--dz`, `--seed`, `--duration`, `--dt`, and `--preset` to change these values. `--no-plots` suppresses PNG generation.

Input diagnostics need NumPy, SciPy and (for plotting) Matplotlib. Full execution additionally requires the actual upstream stack:

* [fastscape-litho](https://github.com/fastscape-lem/fastscape-litho), required source revision `0ce9c7c056b197a2f558343597af7c7375ff6f20`;
* a compatible `fastscape`, `xarray-simlab`, `fastscapelib-fortran`, and their dependencies.

No dependencies are automatically installed by the pipeline. No substitute physics is used. The repository `.venv` was integration-tested with Python 3.12.4, NumPy 2.3.5, SciPy 1.18.1, Numba 0.62.1, xarray 2023.12.0, xarray-simlab 0.5.0, zarr 2.18.7, fastscape 0.1.0, fastscapelib-fortran 2.8.4, and fastscape-litho installed directly from the required Git SHA. Other combinations remain unverified. The adapter follows the pinned `fastscape_litho/fastscape_litho.py` and `notebooks/Folded_Range.ipynb` setup API. Use the opt-in real-backend test below to verify a changed dependency stack.

## Geological inputs

`sedimentary_plateau` has gently tilted alternating mudstone, sandstone and limestone above crystalline basement. `fold_belt` warps these interfaces sinusoidally and applies a broad uplift maximum. `fault_blocks` offsets interfaces between blocks and varies block uplift. `intrusive_massif` inserts an expanding-with-depth granite body with localized uplift. `mosaic` places these four environments in quadrants. Quadrant contacts are abrupt experimental province boundaries. Dimensions, layer thicknesses, fold amplitudes, fault throws and intrusion geometry are explicitly synthetic choices, not reconstructions.

A seeded 9 × 9 × 9 Gaussian control lattice interpolates smooth three-dimensional heterogeneity. Only one floating-point depth slice is generated at a time. The `(y,x,z)` uint8 volume is written as a NumPy memory map. The default 121 depth samples occupy 126877696 bytes (121 MiB), excluding the small `.npy` header. Horizontal temporary fields, model state and library copies require additional memory. Runtime output retains only the final clock sample; backend peak memory and 1024² runtime have not been benchmarked.

Material IDs and provisional erosion/diffusion coefficients are in `config.py` and each manifest. With stream-power exponents m=0.5, n=1, Kr has units yr⁻¹; Kdr and Kds have units m²/yr. These values are illustrative. The model uses upstream `sediment_model_label3D`: multiple-flow routing, differential stream-power incision/transport/deposition and differential linear diffusion. All four edges are fixed at initial elevation zero, and uplift is zero on the edges. There is no marine module or dynamic tectonic deformation of the volume.

## Depth semantics and failure policy

Depth sample k represents `k*dz` downward from each column's initial local surface. Columns move with prescribed uplift. The volume is a material-coordinate reference; its z axis is not a world-elevation axis.

Upstream `TotalErosion.cumulative_height` accumulates **signed net surface lowering**, excluding tectonic uplift and including deposition. It does not track accumulated positive bedrock incision. This adapter preserves that signed field and uses it for a checked **bedrock voxel intercept**: positive cumulative net erosion selects `ceil(cumulative_erosion/dz)`, while finite negative values conservatively clamp to depth index 0, the original top bedrock material. That clamp makes no claim about deposited-sediment lithology, provenance, composition, or stratigraphy. Nonfinite erosion and positive depth exhaustion raise explicit errors before lookup; no negative LUT indexing, silent last-material substitution, or positive-depth clamp is allowed. The last step is checked again during export. Increase depth or shorten the run if the bedrock voxel column is exhausted.

Final `exposed_lithology` is this final bedrock voxel intercept, not a deposited-sediment label or a sediment-corrected bedrock intercept. On cells with negative cumulative net erosion it is the original top bedrock material. The upstream model tracks sediment thickness, but this adapter does not track deposited provenance, composition, or stratigraphy. Channel soil coefficients are spatially uniform (`k_coef_soil=6e-5`, `g_coef_soil=1`); soil diffusivity is **not** uniform: upstream `DifferentialLinearDiffusionForeign` selects `Kds_lab` using the local bedrock voxel-intercept label, not sediment provenance. Strict surface-material interpretation on sediment-covered cells is outside this prototype's assumptions.

## Artifacts

* `manifest.json`: configuration, package versions, required upstream SHA, geometry, units, labels, process parameters, assumptions, completion/failure status, and SHA-256 hashes of completed artifacts.
* `lithology_volume.npy`: immutable initial material-coordinate uint8 `(y,x,z)` voxel volume, loadable with `np.load(..., mmap_mode="r")`.
* `inputs.npz`: initial elevation, uplift, province IDs and initial surface lithology.
* `inputs.png`: initial elevation, uplift, geological provinces, surface labels and two central depth sections. Map axes are node indices; depth section rows are depth indices (multiply by dz).
* Full runs add `surface_fields.npz`: final elevation (m), drainage area (m²), last-step erosion rate (m/yr), signed cumulative erosion (m), and final bedrock voxel-intercept lithology. Erosion rate is the final upstream `erosion__height` divided by the actual final master-clock step duration, including a shortened final step or a run shorter than `dt`. Positive means net lowering; negative means net deposition. Both cumulative erosion and final erosion rate remain signed; neither is estimated from elevation change without uplift correction.
* `surface.png`: elevation, log drainage area, signed last-step erosion rate, and bedrock voxel-intercept material map.
* `surface.flem`: surface elevation, drainage and signed erosion rate for the existing viewer. FLEM carries no lithology volume or material IDs. Water rendering is disabled; sea level is not simulated.

Upstream `fastscape.processes.erosion.TotalErosion.run_step` sums process erosion heights into `height` (m) and adds that increment to `cumulative_height`; its `rate` is `height/step_delta`. The adapter uses this same rate definition from the final snapshot. xarray-simlab writes step snapshots after `run_step`, before `finalize_step`, and also writes a terminal snapshot. Consequently the last two saved cumulative values can duplicate the final state: differencing them is not a valid final-step rate.

Drainage is the upstream routing result from the last process step, evaluated on that step's pre-erosion, uplift-adjusted surface. It is not recomputed on the final updated elevation; this temporal staggering is recorded in the manifest. Final bedrock voxel-intercept labels are recomputed from final signed cumulative erosion rather than exporting the step-start label map.

FLEM v1 matches the existing viewer's loader: 64-byte little-endian `<4sIII8fIf8s` header, then elevation/drainage/erosion as three little-endian float32 C-order `(ny,nx)` arrays. Lengths use `(nx-1)*dx`, `(ny-1)*dx`; extrema describe serialized fields. Signed erosion values are retained.

## Modules and tests

`config.py` owns parameters/materials, `geology.py` generates inputs and bounds-checked bedrock intersections, `backend.py` isolates real upstream integration, `export.py` owns the viewer protocol, `plotting.py` owns diagnostics, and `__main__.py` orchestrates filesystem/manifest handling. These boundaries allow later geology, backend or export replacement independently.

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_lem_litho_pipeline.py -v
LEM_LITHO_INTEGRATION=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_lem_litho_pipeline.py -v
```

Tests cover deterministic presets, geometry, memory-map equivalence, positive ceil lookup, finite-negative depth-zero clamping, nonfinite and exhaustion errors, independent nonsquare FLEM parsing, validation/overwrite rejection, short final intervals, dependency errors, and input-only execution. A mocked adapter regression checks signed final-step height conversion despite duplicate cumulative snapshots, final-only output requests, and regular, shortened, and single-step durations. The opt-in integration test invokes the real backend with a shortened final step, permits deposition through the conservative bedrock intercept, and asserts nonzero erosion. No mocked model output is presented as integration evidence.
