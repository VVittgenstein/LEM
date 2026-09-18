# Native display interface

The Qt frontend owns the loaded `TerrainDataset`. Each voxel display owns one native process, a foreign-window container and a temporary input directory under the ignored `output/viewer/sessions`. The renderer does not modify the source arrays.

## LVT1 payload

Little-endian header, Python `struct` format `<4sIIII6d`, 68 bytes:

| Field | Meaning |
|---|---|
| magic | `LVT1` |
| nx, ny | Display columns and rows |
| levels | Height quantization levels, 2..4096 |
| flags | Bit 0: water enabled; bit 1: material appearance |
| dx, dy | Sampled horizontal spacing in metres |
| minimum, maximum | Source elevation extrema in metres |
| water | Water level in the same elevation datum, metres |
| exaggeration | Positive vertical display multiplier |

The header is followed by row-major float32 elevation, drainage and erosion arrays, then one RGBA8 colour per column. Missing optional drainage/erosion inputs have zero values only inside this display adapter; they do not become dataset channels. NaN elevation columns remain empty. Scientific colours and logarithmic transforms are calculated by the existing Python channel and colour-scale code.

The original normalized height quantization is retained. Top voxel index `q` maps to `minimum + q * (maximum-minimum)/(levels-1)` metres. Mesh coordinates use one common metres-per-scene-unit factor, with the vertical display multiplier applied separately. Cell centres align with the source grid nodes. The bottom support layer uses a fixed depth for a given horizontal sampling, so changing height levels also preserves the displayed base. Flat inputs have one ground surface at their original elevation. Water above the elevation range uses its physical elevation without allocating an arbitrarily deep water volume.

## Control and lifecycle

Commands are UTF-8 newline-delimited records on stdin. Quoted paths use double quotes and backslash escaping. `LOAD "path" revision reset` loads one payload. `CAMERA`, `RESET`, `GRID`, `HUD`, `PROFILER`, `FPS`, `CULL`, `PALETTE`, `POSE`, `ACTIVE`, `KEY`, `FOCUS`, `CAPTURE` and `QUIT` control the existing native components. The Python process limits queued geometry work to one active load and the latest pending request.

Native events are JSON records prefixed by `LEM_EVENT ` on stdout. Other stdout lines are diagnostic logs. `ready` supplies the native window handle; `loaded` acknowledges an input revision; `state` returns camera and control state; `error` reports a failure. Input files are removed after acknowledgement. A failed data load leaves the previous valid native mesh available and displays the error in the corresponding slot.

Mode changes explicitly close the native process. Shutdown first requests `QUIT`, then terminates an unresponsive owned process. Input arrays, dimensions, size arithmetic and finite scales are checked before allocation. The fixed 512 MiB dense-voxel cap has been removed; voxel indexes and diagnostic counts use 64-bit types in the Windows build. Actual capacity depends on available resources. Allocation exceptions from the grid or parallel CPU meshing are reported through the error event. Native OpenGL resources are released before the context closes. One failing renderer does not close the other display or the Qt application.

`POSE` and the `state.pose` record now include the vertical field of view as the seventeenth value, after fly speed. Legacy sixteen-value poses load with a 45-degree field of view. Fly-mode wheel input changes this angle from 1 to 90 degrees while preserving camera position and movement speed. Physical scene-unit conversion leaves the angle unchanged. `RESET` restores 45 degrees.

The legacy two-surface camera synchronization remains available. Mixed renderer pairs and two voxel displays have independent cameras. GPU command submission and presentation timings in the native performance panel are CPU wall-clock measurements; they are not GPU timer-query measurements.
