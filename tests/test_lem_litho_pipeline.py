import json
import os
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
import numpy as np
from lem_litho_pipeline.config import Config, PRESETS
from lem_litho_pipeline.geology import generate, exposed_labels
from lem_litho_pipeline.backend import BackendUnavailable, load_backend, clock, run
from lem_litho_pipeline.export import write_flem
from lem_litho_pipeline.__main__ import execute


class GeologyTests(unittest.TestCase):
    def test_defaults_geometry_and_validation(self):
        c = Config()
        self.assertEqual(c.shape, (1024, 1024))
        self.assertEqual(c.length, (102300, 102300))
        self.assertEqual(c.nz, 121)
        for kwargs in ({"nx": 2}, {"dx": float("nan")}, {"dt": 0}, {"seed": -1},
                       {"depth": 101, "dz": 50}, {"preset": "unknown"}):
            with self.assertRaises(ValueError):
                Config(**kwargs)

    def test_seed_and_all_presets(self):
        for preset in PRESETS:
            c = Config(nx=17, ny=13, depth=1000, dz=50, preset=preset)
            a, b = generate(c), generate(c)
            np.testing.assert_array_equal(a.labels, b.labels)
            np.testing.assert_array_equal(a.uplift, b.uplift)
            np.testing.assert_array_equal(a.elevation, b.elevation)
            self.assertEqual(a.labels.shape, (13, 17, 21))
            self.assertEqual(a.labels.dtype, np.uint8)
            self.assertGreater(len(np.unique(a.labels)), 2)
            self.assertTrue(np.any(a.labels[:, :, 0] != a.labels[:, :, -1]))
            self.assertTrue(np.all(a.uplift >= 0))
            self.assertTrue(np.all(a.uplift[[0, -1], :] == 0))
        other = generate(Config(nx=17, ny=13, depth=1000, seed=22))
        self.assertFalse(np.array_equal(a.labels, other.labels))

    def test_memmap_matches_memory(self):
        c = Config(nx=7, ny=5, depth=200)
        with tempfile.TemporaryDirectory() as tmp:
            a = generate(c, Path(tmp) / "volume.npy")
            np.testing.assert_array_equal(a.labels, generate(c).labels)
            self.assertIsInstance(a.labels, np.memmap)

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
        # Adapter contract test, not a simulation of the upstream physics.
        # A driver snapshot after the last run_step and its terminal snapshot
        # have identical cumulative erosion, but a nonzero step height.
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

    def test_inputs_only_and_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "result"
            with patch("lem_litho_pipeline.__main__.load_backend", side_effect=AssertionError("backend imported")):
                execute(Config(nx=9, ny=7, depth=200), output, inputs_only=True, plots=False)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["status"], "inputs_only")
            self.assertIn("lithology_volume.npy", manifest["sha256"])
            self.assertFalse((output / "surface.flem").exists())
            with self.assertRaises(FileExistsError):
                execute(Config(nx=9, ny=7), output, inputs_only=True, plots=False)

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
