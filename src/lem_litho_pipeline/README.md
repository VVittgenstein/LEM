# `lem_litho_pipeline`

Independent experimental code for generating a finite island input, continuous uplift, a three-dimensional lithology volume, and optional Fastscape surface evolution. It does not change the current strategy or the existing LEM pipelines. The landform names in this module identify synthetic planning classes. They do not constitute ecological biomes, calibrated geomorphological classifications, or detected final landforms.

## Run

From the repository root, make `src` importable:

```sh
PYTHONPATH=src python -m lem_litho_pipeline --help
PYTHONPATH=src python -m lem_litho_pipeline --inputs-only \
  --nx 256 --ny 256 --depth 1000 --output output/litho-input-check
PYTHONPATH=src python -m lem_litho_pipeline --output output/litho-run
```

PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m lem_litho_pipeline --inputs-only --output output\litho-input-check
```

Every execution requires a new output directory. Existing directories and FLEM files are not overwritten. A failed execution retains its partial artifacts and a manifest with `status: failed`. Full-run dependency availability is checked before the output directory is created.

## Defaults and configuration

| Parameter | Default | Meaning |
|---|---:|---|
| `nx`, `ny` | 1024, 1024 | Horizontal node counts |
| `dx` | 100 m | Isotropic horizontal node spacing |
| `depth`, `dz` | 6000 m, 50 m | Column depth and depth sampling |
| `duration`, `dt` | 50000 yr, 1000 yr | Evolution duration and master-clock step |
| `seed` | 21 | Reproducible random seed |
| `preset` | `mosaic` | Geological warp mixture |
| `target_land_fraction` | 0.62 | Requested initial fraction of cells above water level |
| `ocean_buffer_fraction` | 0.035 | Minimum rectangular eligibility margin on every edge |
| `uplift_scale` | 1.0 | Multiplier applied to the generated uplift field before evolution |
| `initial_relief_scale` | 1.0 | Multiplier applied to positive initial relief above the coastal platform |
| `erodibility_scale` | 1.0 | Multiplier applied to all material `Kr` values |
| `diffusion_scale` | 1.0 | Multiplier applied to material hillslope-diffusion coefficients |
| `lithology_seed_offset` | 0 | Independent offset for randomized lithology while preserving terrain seed |

`target_land_fraction` accepts 0.50 through 0.75. `ocean_buffer_fraction` accepts values above 0 and below 0.2. On adequately sized grids, the initial land count matches the requested fraction to within one cell. Very small test grids can lack enough interior cells after retaining one ocean cell on every edge. Those grids fill their available interior and record `target_land_fraction_reached: false` plus `maximum_land_fraction_with_buffer` in the manifest.

The default horizontal node span is 102300 m along each axis. The scale parameters retain neutral defaults so a candidate experiment does not silently redefine the base configuration. Older, higher-relief 1024 by 1024 trials pass explicit duration, uplift, initial-relief, and erodibility scales on the command line. Current accepted candidate constraints include a final land fraction from 0.50 through 0.75 and a total elevation range from 4 through 6 km. These controls alter model inputs and coefficients before simulation; no output elevation rescaling is performed.

## Island, planning fields, and uplift

The initial land mask is one seeded star-shaped island surrounded by ocean on all four edges. A rotated anisotropic radial coordinate, low-order angular harmonics, seeded displacement, and occupancy threshold determine its planform. The configured ocean margin defines cells that cannot become land. This margin is rectangular, so extreme target, buffer, aspect, and seed combinations can still approach the eligibility boundary. Input diagnostics report all four edge checks and four-neighbour component statistics.

Each sample selects 3 through 5 names from `mountain`, `hills`, `plain`, `canyon`, and `delta`. Seeded spatial influence fields produce continuous weights. `landform` stores only the locally dominant planning ID for inspection, while `landform_weights` stores the continuous mixture used in input construction. Ocean uses sentinel 255 and is masked in the planning plot. `planned_landforms` records selected input classes. It does not report classes detected in the evolved output.

The initial elevation and uplift use two to four curved ridge systems. Each system uses a correlated transverse random walk, multiple sinusoidal curvature scales, longitudinal amplitude modulation, slowly varying core and flank widths, and smooth band-limited spatial modulation. End amplitudes taper continuously. Landform weights modify relief and uplift continuously. The plain and delta planning rates and relief factors are lower than the mountain, hills, and canyon factors. A positive coastal platform supplies a small initial elevation margin. Uplift tapers continuously to zero near the initial coastline and is zero in the ocean.

These are synthetic construction rules. They do not guarantee that every selected planning class remains visually separable after evolution. In particular, output landform detection has not been implemented.

## Geological presets and 3D lithology

The presets are `sedimentary_plateau`, `fold_belt`, `fault_blocks`, `intrusive_massif`, and `mosaic`. Four seeded continuous province weights construct spatial geological environments. `mosaic` combines those weights continuously; it does not use fixed quadrants. The other presets emphasize one structural warp while retaining a smaller mixed contribution. `province` stores the dominant diagnostic ID.

The `(y, x, z)` uint8 lithology volume is generated one depth slab at a time. Layer interfaces depend on horizontal warp, smooth horizontal texture, and depth-varying phase. Alternating mudstone, sandstone, and limestone pass into crystalline basement; a seeded intrusive body expands with depth. Thus the field varies horizontally and vertically. The default 121 depth samples use 126877696 bytes for voxel data, excluding the small NumPy header and runtime temporary arrays.

Depth sample `k` means `k*dz` downward from each column's initial local surface. Columns co-uplift in the backend. This is a material-coordinate volume, not a world-elevation volume. Dynamic faulting and intrusive growth during evolution are absent.

## Backend and process limits

Input-only mode requires NumPy and SciPy, plus Matplotlib when plots are enabled. Full execution requires the actual upstream stack:

* [fastscape-litho](https://github.com/fastscape-lem/fastscape-litho) at source revision `0ce9c7c056b197a2f558343597af7c7375ff6f20`;
* compatible `fastscape`, `xarray-simlab`, `fastscapelib-fortran`, and their dependencies.

No dependency is installed automatically and no substitute physics is used. Package metadata cannot establish the installed Git SHA, so the user must verify the upstream checkout.

The adapter uses `sediment_model_label3D`, multiple-flow routing, differential stream-power erosion and sediment transport, and differential linear diffusion. Four boundaries use the upstream `fixed_value` status at their initial negative ocean elevation. The pipeline exports a zero-metre water level for visualization. The backend currently has no marine erosion cutoff, wave or tidal transport, shoreface process, or marine sedimentation model. Rivers can continue through cells below zero metres, producing submarine channels. This limitation is recorded because it affects final coastlines and drainage diagnostics.

`delta` currently specifies a low-uplift, low-relief input planning region. The pipeline does not detect a final delta and lacks the marine and mouth-deposition processes required to establish a process-based delta claim. Final output metrics therefore contain no detected-landform count.

Material coefficients in `config.py` and the manifest are provisional synthetic parameters. They have not been calibrated against observations. The 10 kyr scaled default and revised ridge input require further multi-seed validation.

## Depth lookup and erosion semantics

Upstream cumulative erosion is signed net surface lowering, excludes tectonic uplift, and includes deposition. Positive values select `ceil(cumulative_erosion/dz)` in the initial lithology column. Finite negative values select depth index zero as a conservative original-bedrock intercept. Nonfinite erosion and positive column exhaustion raise errors. The exposed label does not identify deposited sediment provenance, composition, or stratigraphy.

The exported erosion rate is the final upstream erosion-height increment divided by the actual final clock interval. It supports shortened final intervals and a duration shorter than `dt`. Positive values indicate net lowering and negative values indicate net deposition. Drainage is the upstream final routing state before the final surface update; the adapter does not recompute drainage on the final updated elevation.

## Diagnostics and plots

Input diagnostics in `manifest.json` include:

* actual and target land fractions, target-reached status, and maximum fraction allowed by the buffer;
* ocean checks on all four edges;
* four-neighbour land component count and principal-component fraction;
* selected and represented planning IDs with represented land fractions;
* elevation and uplift summaries plus neighbouring-cell uplift jumps;
* surface lithology IDs.

Full runs additionally report:

* final land fraction and whether it lies in 0.50 through 0.75;
* total elevation range, whether it lies in 4000 through 6000 m, and land elevation quantiles;
* final four-neighbour land components, principal-component fraction, and edge-ocean checks;
* summaries for full-domain and land-only slope and 5 km local relief;
* elevation, drainage area, river display threshold, coastline cell count, erosion, cumulative erosion, and exposed lithology IDs.

`inputs.png` contains initial elevation with hillshade and coastline, continuous uplift, dominant planning IDs with ocean masked, dominant geological province, surface lithology, and a central lithology section. `inputs_3d.png` renders the initial elevation surface. `surface.png` contains final shaded relief with coastline and an upper-five-percent drainage overlay, drainage area, slope, local relief, signed final-interval erosion, and exposed lithology. `surface_3d.png` renders the evolved elevation surface.

The local-relief channel uses a circular maximum/minimum footprint of approximately 5 km diameter.

## Artifacts

* `manifest.json`: schema version, configuration, package versions, required upstream revision, geometry, units, assumptions, diagnostics, status, and completed-artifact SHA-256 hashes.
* `lithology_volume.npy`: initial uint8 `(y, x, z)` material-coordinate volume, loadable using `np.load(..., mmap_mode="r")`.
* `inputs.npz`: `elevation`, `uplift`, `province`, `landform`, `landform_weights`, `land_mask`, and `surface_lithology`.
* `inputs.png` and `inputs_3d.png`: input review figures when plotting is enabled.
* `surface_fields.npz`: full-run final elevation, drainage area, signed final-interval erosion rate, signed cumulative erosion, and bedrock voxel-intercept lithology.
* `surface.png` and `surface_3d.png`: full-run surface review figures when plotting is enabled.
* `surface.flem`: FLEM v1 elevation, drainage, and signed erosion-rate fields with `water_level=0` explicitly enabled. FLEM does not carry the lithology volume or material IDs.

FLEM v1 uses a 64-byte little-endian `<4sIII8fIf8s` header followed by three little-endian float32 C-order `(ny,nx)` arrays. Lengths use `(nx-1)*dx` and `(ny-1)*dx`.

## Tests

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_lem_litho_pipeline.py -v
LEM_LITHO_INTEGRATION=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_lem_litho_pipeline.py -v
```

The unit suite covers defaults, validation, determinism, presets, main-island geometry, continuous uplift, planning weights, small-grid fallback, memory-map equivalence, 3D label lookup, diagnostic functions, FLEM parsing and water-level metadata, manifest output, overwrite rejection, backend dependency errors, and final-clock rate handling. The opt-in test invokes the real backend. It requires the user-prepared pinned environment and does not replace multi-seed output validation.
