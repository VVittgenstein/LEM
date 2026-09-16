import json
import os
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
import numpy as np
from scipy.ndimage import label
from lem_litho_pipeline.config import Config, PRESETS
from lem_litho_pipeline.geology import generate, exposed_labels
from lem_litho_pipeline.backend import BackendUnavailable, load_backend, clock, run
from lem_litho_pipeline.diagnostics import (coastline_mask, input_diagnostics,
                                             output_diagnostics, terrain_derivatives)
from lem_litho_pipeline.export import write_flem
from lem_litho_pipeline.__main__ import execute
from lem_litho_pipeline.plotting import terrain_3d_geometry


class GeologyTests(unittest.TestCase):
    def test_defaults_geometry_and_validation(self):
        c = Config()
        self.assertEqual(c.shape, (1024, 1024))
        self.assertEqual(c.length, (102300, 102300))
        self.assertEqual(c.dx, 100.0)
        self.assertEqual(c.duration, 50000.0)
        self.assertEqual(c.uplift_scale, 1.0)
        self.assertEqual(c.initial_relief_scale, 1.0)
        self.assertEqual(c.erodibility_scale, 1.0)
        self.assertEqual(c.diffusion_scale, 1.0)
        self.assertEqual(c.lithology_seed_offset, 0)
        self.assertEqual(c.nz, 121)
        for kwargs in ({"nx": 2}, {"dx": float("nan")}, {"dt": 0}, {"seed": -1},
                       {"depth": 101, "dz": 50}, {"preset": "unknown"},
                       {"target_land_fraction": 0.49}, {"ocean_buffer_fraction": 0.25},
                       {"uplift_scale": 0}, {"initial_relief_scale": 11},
                       {"erodibility_scale": 5}, {"diffusion_scale": 21},
                       {"lithology_seed_offset": -1}):
            with self.assertRaises(ValueError):
                Config(**kwargs)

    def test_seed_and_all_presets(self):
        signatures = []
        for preset in PRESETS:
            c = Config(nx=65, ny=57, depth=1000, dz=50, preset=preset)
            a, b = generate(c), generate(c)
            np.testing.assert_array_equal(a.labels, b.labels)
            np.testing.assert_array_equal(a.uplift, b.uplift)
            np.testing.assert_array_equal(a.elevation, b.elevation)
            self.assertEqual(a.labels.shape, (57, 65, 21))
            self.assertEqual(a.labels.dtype, np.uint8)
            self.assertGreater(len(np.unique(a.labels)), 2)
            self.assertTrue(np.any(a.labels[:, :, 0] != a.labels[:, :, -1]))
            self.assertTrue(np.all(a.uplift >= 0))
            self.assertTrue(np.all(a.uplift[[0, -1], :] == 0))
            self.assertGreaterEqual(len(a.planned_landforms), 3)
            self.assertLessEqual(len(a.planned_landforms), 5)
            self.assertIn("mountain", a.planned_landforms)
            self.assertIn("plain", a.planned_landforms)
            signatures.append((a.elevation.copy(), a.uplift.copy()))
        for left, right in zip(signatures, signatures[1:]):
            self.assertFalse(np.array_equal(left[0], right[0]))
            self.assertFalse(np.array_equal(left[1], right[1]))
        other = generate(Config(nx=65, ny=57, depth=1000, seed=22))
        self.assertFalse(np.array_equal(signatures[-1][0], other.elevation))

    def test_island_contract_and_continuous_uplift(self):
        for seed in range(6):
            with self.subTest(seed=seed):
                c = Config(nx=160, ny=144, depth=200, seed=seed)
                inputs = generate(c)
                land = inputs.elevation > 0
                self.assertTrue(np.all(inputs.elevation[[0, -1], :] < 0))
                self.assertTrue(np.all(inputs.elevation[:, [0, -1]] < 0))
                self.assertAlmostEqual(land.mean(), c.target_land_fraction, delta=1 / land.size)
                _, count = label(land, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]))
                self.assertEqual(count, 1)
                self.assertGreaterEqual(len(inputs.planned_landforms), 3)
                self.assertLessEqual(len(inputs.planned_landforms), 5)
                self.assertIn("mountain", inputs.planned_landforms)
                self.assertIn("plain", inputs.planned_landforms)
                self.assertEqual(inputs.landform_weights.shape, (*c.shape, len(inputs.planned_landforms)))
                self.assertEqual(inputs.ridge_field.shape, c.shape)
                self.assertGreaterEqual(inputs.ridge_system_count, 2)
                self.assertLessEqual(inputs.ridge_system_count, 4)
                self.assertGreater(np.max(inputs.ridge_field), 0.5)
                self.assertLess(np.mean(inputs.ridge_field > 0.35), 0.4)
                np.testing.assert_allclose(inputs.landform_weights.sum(axis=2), 1.0, atol=2e-7)
                jumps = np.concatenate((np.abs(np.diff(inputs.uplift, axis=0)).ravel(),
                                        np.abs(np.diff(inputs.uplift, axis=1)).ravel()))
                self.assertLess(np.percentile(jumps, 99), 5e-4)

    def test_mosaic_has_no_fixed_quadrant_seams(self):
        c = Config(nx=161, ny=145, depth=200, seed=31, preset="mosaic")
        inputs = generate(c)
        dy = np.abs(np.diff(inputs.uplift, axis=0))
        dx = np.abs(np.diff(inputs.uplift, axis=1))
        center_y, center_x = c.ny // 2, c.nx // 2
        self.assertLess(np.mean(dy[center_y - 1]), np.percentile(dy, 99.9) + 1e-12)
        self.assertLess(np.mean(dx[:, center_x - 1]), np.percentile(dx, 99.9) + 1e-12)
        upper_left = inputs.province[:center_y, :center_x]
        self.assertGreater(len(np.unique(upper_left)), 1)

    def test_small_grids_retain_ocean_ring_without_partition_failure(self):
        for ny, nx, expected in ((3, 3, 1), (3, 5, 3), (5, 7, 15), (7, 9, 35)):
            with self.subTest(shape=(ny, nx)):
                c = Config(nx=nx, ny=ny, depth=200)
                inputs = generate(c)
                self.assertEqual(int(inputs.land_mask.sum()), expected)
                self.assertTrue(np.all(~inputs.land_mask[[0, -1], :]))
                self.assertTrue(np.all(~inputs.land_mask[:, [0, -1]]))
                metrics = input_diagnostics(c, inputs)
                self.assertFalse(metrics["target_land_fraction_reached"])
                self.assertEqual(metrics["land_fraction"], metrics["maximum_land_fraction_with_buffer"])

    def test_memmap_matches_memory(self):
        c = Config(nx=7, ny=5, depth=200)
        with tempfile.TemporaryDirectory() as tmp:
            a = generate(c, Path(tmp) / "volume.npy")
            np.testing.assert_array_equal(a.labels, generate(c).labels)
            self.assertIsInstance(a.labels, np.memmap)

    def test_lithology_offset_changes_geology_without_changing_terrain_geometry(self):
        base = generate(Config(nx=65, ny=57, depth=200, seed=9, lithology_seed_offset=0))
        changed = generate(Config(nx=65, ny=57, depth=200, seed=9, lithology_seed_offset=4))
        np.testing.assert_array_equal(base.land_mask, changed.land_mask)
        np.testing.assert_array_equal(base.landform, changed.landform)
        np.testing.assert_array_equal(base.ridge_field, changed.ridge_field)
        self.assertFalse(np.array_equal(base.labels, changed.labels))
        self.assertFalse(np.array_equal(base.province, changed.province))

    def test_terrain_3d_geometry_uses_physical_kilometre_spans(self):
        elevation = np.array([[-1000.0, 0.0, 1000.0], [0.0, 1000.0, 3000.0]])
        x, y, z, spans = terrain_3d_geometry(elevation, dx=100.0, stride=1)
        np.testing.assert_allclose(x, [0.0, 0.1, 0.2])
        np.testing.assert_allclose(y, [0.0, 0.1])
        np.testing.assert_allclose(z, elevation / 1000.0)
        np.testing.assert_allclose(spans, (0.2, 0.1, 4.0))

    def test_guard_ceil_and_negative_clamp(self):
        labels = np.broadcast_to(np.array([2, 1, 4], dtype=np.uint8), (3, 4, 3)).copy()
        for depth, expected in ((-1000, 2), (-0.001, 2), (0, 2), (0.1, 1),
                                (50, 1), (50.1, 4), (100, 4)):
            self.assertTrue(np.all(exposed_labels(labels, depth, 50) == expected))
        erosion = np.array([[-1, 0, 0.1, 50.1]] * 3)
        np.testing.assert_array_equal(exposed_labels(labels, erosion, 50),
                                      np.array([[2, 2, 1, 4]] * 3))
        for bad in (100.1, float("nan"), float("inf"), -float("inf")):
            with self.assertRaises(ValueError):
                exposed_labels(labels, bad, 50)

    def test_diagnostic_functions(self):
        y, x = np.mgrid[:9, :11]
        elevation = 2 * x + 3 * y - 20
        derivatives = terrain_derivatives(elevation, 2.0)
        np.testing.assert_allclose(derivatives["slope"], np.sqrt(3.25))
        self.assertTrue(np.all((derivatives["hillshade"] >= 0) &
                               (derivatives["hillshade"] <= 1)))
        self.assertGreater(derivatives["local_relief"].max(), 0)
        coast = coastline_mask(elevation)
        self.assertTrue(coast.any())
        c = Config(nx=65, ny=57, depth=200)
        metrics = input_diagnostics(c, generate(c))
        self.assertAlmostEqual(metrics["land_fraction"], c.target_land_fraction,
                               delta=1 / (c.nx * c.ny))
        self.assertEqual(metrics["land_component_count_4"], 1)
        self.assertEqual(metrics["planned_landform_count"], len(metrics["planned_landforms"]))
        self.assertEqual(metrics["represented_landform_count"],
                         len(metrics["represented_landform_ids"]))
        fields = {
            "elevation": generate(c).elevation,
            "drainage_area": np.ones(c.shape),
            "erosion_rate": np.zeros(c.shape),
            "cumulative_erosion": np.zeros(c.shape),
            "exposed_lithology": np.zeros(c.shape, dtype=int),
        }
        output = output_diagnostics(c, fields)
        self.assertTrue(output["land_fraction_in_requested_range"])
        self.assertEqual(output["land_component_count_4"], 1)
        self.assertIn("land_slope_m_per_m", output)
        self.assertIn("land_slope_angle_degrees", output)
        self.assertIn("land_slope_above_45deg_fraction", output)
        self.assertIn("elevation_range_m", output)
        self.assertIn("land_elevation_m", output)


class FlemTests(unittest.TestCase):
    def test_independent_nonsquare_parse(self):
        h = np.arange(15, dtype=float).reshape(3, 5)[:, ::-1]
        area = h * 100
        erosion = (h - 7) / 1000
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.flem"
            write_flem(path, h, area, erosion, 100)
            raw = path.read_bytes()
            self.assertEqual(len(raw), 64 + 3 * 15 * 4)
            header = struct.unpack("<4sIII8fIf8s", raw[:64])
            self.assertEqual(header[:4], (b"FLEM", 1, 5, 3))
            self.assertEqual(header[4:8], (400, 200, 0, 14))
            self.assertEqual(header[8:10], (0, 1400))
            self.assertAlmostEqual(header[10], -0.007)
            self.assertAlmostEqual(header[11], 0.007)
            self.assertEqual(header[12:], (0, 0, b"\0" * 8))
            data = np.frombuffer(raw, dtype="<f4", offset=64).reshape(3, 3, 5)
            for actual, expected in zip(data, (h, area, erosion)):
                np.testing.assert_array_equal(actual, np.asarray(expected, dtype="<f4"))
            with self.assertRaises(FileExistsError):
                write_flem(path, h, area, erosion, 100)

    def test_explicit_zero_water_level(self):
        fields = np.ones((3, 5))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "water.flem"
            write_flem(path, fields, fields, fields, 100, water_level=0.0)
            header = struct.unpack("<4sIII8fIf8s", path.read_bytes()[:64])
            self.assertEqual(header[12], 1)
            self.assertEqual(header[13], 0.0)

    def test_invalid_fields(self):
        a = np.ones((3, 5))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.flem"
            for fields, dx in (((a, a[:, :2], a), 1), ((a, -a, a), 1),
                               ((a * np.nan, a, a), 1), ((a, a, a), -1)):
                with self.assertRaises(ValueError):
                    write_flem(path, *fields, dx)
            self.assertFalse(path.exists())


class ExecutionTests(unittest.TestCase):
    def test_lazy_dependency_error(self):
        with patch("lem_litho_pipeline.backend.importlib.import_module", side_effect=ModuleNotFoundError("missing")):
            with self.assertRaisesRegex(BackendUnavailable, "inputs-only"):
                load_backend()

    def test_clock(self):
        np.testing.assert_array_equal(clock(2500, 1000), [0, 1000, 2000, 2500])
        np.testing.assert_array_equal(clock(500, 1000), [0, 500])

    def test_final_step_rate_uses_height_not_duplicate_cumulative(self):
        for duration in (2500, 500, 2000):
            with self.subTest(duration=duration):
                c = Config(nx=5, ny=3, depth=200, dt=1000, duration=duration)
                height = np.arange(15, dtype=float).reshape(c.shape) - 7
                cumulative = np.arange(15, dtype=float).reshape(c.shape) - 7
                values = {"erosion__height": height,
                          "erosion__cumulative_height": cumulative,
                          "topography__elevation": np.ones(c.shape),
                          "drainage__area": np.ones(c.shape)}

                class Snapshot:
                    def __init__(self, data):
                        self.values = data

                    def isel(self, **index):
                        self_test.assertEqual(index, {"save": -1})
                        return Snapshot(self.values[-1])

                    def transpose(self, *dims):
                        self_test.assertEqual(dims, ("y", "x"))
                        return self

                self_test = self
                xs = MagicMock()
                xs.process.side_effect = lambda cls: cls

                def create_setup(**kwargs):
                    np.testing.assert_array_equal(kwargs["clocks"]["save"], [duration])
                    self.assertEqual(kwargs["output_vars"]["erosion__height"], "save")
                    expected_kr = [material["Kr"] * c.erodibility_scale
                                   for material in __import__("lem_litho_pipeline.config",
                                                              fromlist=["MATERIALS"]).MATERIALS]
                    np.testing.assert_allclose(kwargs["input_vars"]["spl__Kr_lab"], expected_kr)
                    result = {name: Snapshot(np.stack([value, value]))
                              for name, value in values.items()}
                    setup = MagicMock()
                    setup.xsimlab.run.return_value = result
                    return setup

                xs.create_setup.side_effect = create_setup
                litho = SimpleNamespace(Label3D=type("Label3D", (), {}),
                                        sediment_model_label3D=MagicMock())
                main = SimpleNamespace(SurfaceTopography=object)
                with patch("lem_litho_pipeline.backend.load_backend", return_value=(xs, litho)), \
                        patch.dict("sys.modules", {"fastscape.processes.main": main}):
                    fields = run(c, generate(c))
                interval = 1000 if duration == 2000 else 500
                np.testing.assert_allclose(fields["erosion_rate"], height / interval)
                np.testing.assert_array_equal(fields["cumulative_erosion"], cumulative)

    def test_uplift_and_erodibility_scales(self):
        base = Config(nx=65, ny=57, depth=200)
        scaled = Config(nx=65, ny=57, depth=200, uplift_scale=0.4)
        np.testing.assert_allclose(generate(scaled).uplift, generate(base).uplift * 0.4)
        relief = generate(Config(nx=65, ny=57, depth=200, initial_relief_scale=3.0))
        self.assertGreater(relief.elevation.max(), generate(base).elevation.max() * 2.5)

    def test_inputs_only_and_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "result"
            with patch("lem_litho_pipeline.__main__.load_backend", side_effect=AssertionError("backend imported")):
                execute(Config(nx=65, ny=57, depth=200), output, inputs_only=True, plots=False)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["status"], "inputs_only")
            self.assertEqual(manifest["schema_version"], 2)
            self.assertIn("input_diagnostics", manifest)
            self.assertIn("planned_landforms", manifest["input_diagnostics"])
            self.assertEqual(manifest["geometry"]["water_level_m"], 0.0)
            self.assertIn("lithology_volume.npy", manifest["sha256"])
            self.assertFalse((output / "surface.flem").exists())
            saved = np.load(output / "inputs.npz")
            self.assertIn("landform_weights", saved.files)
            self.assertIn("ridge_field", saved.files)
            with self.assertRaises(FileExistsError):
                execute(Config(nx=65, ny=57), output, inputs_only=True, plots=False)

    @unittest.skipUnless(os.environ.get("LEM_LITHO_INTEGRATION") == "1", "opt-in real backend integration")
    def test_real_backend(self):
        c = Config(nx=33, ny=25, depth=1000, dt=1000, duration=1500)
        inputs = generate(c)
        fields = run(c, inputs)
        self.assertEqual(fields["elevation"].shape, (25, 33))
        self.assertTrue(np.all(np.isfinite(fields["erosion_rate"])))
        self.assertTrue(np.any(fields["erosion_rate"] > 0))
        self.assertTrue(np.any(fields["erosion_rate"] < 0))
        negative = fields["cumulative_erosion"] < 0
        self.assertTrue(np.any(negative))
        np.testing.assert_array_equal(fields["exposed_lithology"][negative],
                                      inputs.labels[:, :, 0][negative])
        self.assertTrue(np.all(fields["drainage_area"] >= 0))


if __name__ == "__main__":
    unittest.main()
