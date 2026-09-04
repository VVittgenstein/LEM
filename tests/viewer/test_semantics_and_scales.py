"""Tests for channel semantics, banded colour scales, meta.json loading, and the new views."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from lem_viewer.colormaps import BandedScale, banded_colors, format_edge
from lem_viewer.loaders.npy_loader import NpyLoader
from lem_viewer.semantics import (
    KIND_DRAINAGE_AREA,
    KIND_ELEVATION,
    KIND_GENERIC,
    display_array,
    find_elevation_channel,
    infer_kind,
    inverse_display,
)


class TestSemantics:
    @pytest.mark.parametrize(
        "name,kind",
        [
            ("elevation", KIND_ELEVATION),
            ("r1_K1e-05_elev_FS_elev", KIND_ELEVATION),
            ("topo", KIND_ELEVATION),
            ("r1_K1e-05_elev_da_FS_da", KIND_DRAINAGE_AREA),
            ("drainage_area", KIND_DRAINAGE_AREA),
            ("sediment", KIND_GENERIC),
            ("alpha", KIND_GENERIC),
        ],
    )
    def test_infer_kind(self, name: str, kind: str):
        assert infer_kind(name) == kind

    def test_display_array_log10_masks_nonpositive(self):
        arr = np.array([[1.0, 10.0], [0.0, -5.0]])
        out = display_array(arr, "log10")
        assert out[0, 0] == pytest.approx(0.0)
        assert out[0, 1] == pytest.approx(1.0)
        assert np.isnan(out[1, 0]) and np.isnan(out[1, 1])
        assert inverse_display(7.0, "log10") == pytest.approx(1e7)
        assert inverse_display(7.0, "linear") == pytest.approx(7.0)


class TestBandedScale:
    def test_edges_and_band_index(self):
        s = BandedScale(0.0, 12.0, levels=12, palette="fem")
        assert len(s.edges) == 13
        idx = s.band_index(np.array([0.0, 0.5, 11.99, 12.0, np.nan]))
        assert idx.tolist() == [0, 0, 11, 11, -1]

    def test_rgba_shapes_and_nan_transparent(self):
        s = BandedScale.from_array(np.array([[1.0, 2.0], [3.0, np.nan]]), levels=4)
        rgba = s.rgba(np.array([[1.0, 2.0], [3.0, np.nan]]))
        assert rgba.shape == (2, 2, 4)
        assert rgba[1, 1, 3] == 0  # NaN -> transparent
        assert rgba[0, 0, 3] == 255

    def test_fem_palette_is_blue_low_red_high(self):
        c = banded_colors("fem", 12)
        low, high = c[0], c[-1]
        assert low[2] > low[0]  # blue dominant at the low end
        assert high[0] > high[2]  # red dominant at the high end

    def test_constant_array_does_not_collapse(self):
        s = BandedScale.from_array(np.full((3, 3), 5.0))
        assert s.vmax > s.vmin

    def test_format_edge_log10_in_data_units(self):
        assert format_edge(7.0, "log10", "m2") == "1e+07 m2"
        assert format_edge(1234.5, "linear", "m") == "1234.5 m"


class TestMetaLoader:
    def _write_run(self, d: Path, dx: float = 1000.0) -> None:
        z = np.linspace(0, 100, 16).reshape(4, 4)
        a = np.logspace(6, 11, 16).reshape(4, 4)
        np.save(d / "elevation.npy", z)
        np.save(d / "drainage_area.npy", a)
        meta = {
            "grid": {"nx": 4, "ny": 4, "dx_m": dx, "dy_m": dx},
            "channels": {
                "elevation": {"file": "elevation.npy", "units": "m", "kind": "elevation"},
                "drainage_area": {"file": "drainage_area.npy", "units": "m2", "kind": "drainage_area", "display": "log10"},
            },
        }
        (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    def test_directory_with_meta(self, tmp_path: Path):
        self._write_run(tmp_path)
        ds = NpyLoader().load(tmp_path)
        assert ds.spacing == (1000.0, 1000.0)
        assert ds.metadata["semantics"] == "meta"
        da = ds.get_channel("drainage_area")
        assert da.kind == KIND_DRAINAGE_AREA and da.transform == "log10" and da.units == "m2"
        assert ds.get_channel("elevation").kind == KIND_ELEVATION
        assert find_elevation_channel(ds) is ds.get_channel("elevation")
        disp = da.display_array()
        assert disp.min() == pytest.approx(6.0) and disp.max() == pytest.approx(11.0)

    def test_single_file_kind_inferred_name_kept(self, tmp_path: Path):
        f = tmp_path / "r1_K1e-05_elev_da_FS_da.npy"
        np.save(f, np.logspace(6, 9, 16).reshape(4, 4))
        ds = NpyLoader().load(f)
        ch = ds.get_channel("r1_K1e-05_elev_da_FS_da")
        assert ch.kind == KIND_DRAINAGE_AREA and ch.transform == "log10"
        assert find_elevation_channel(ds) is None  # inferred kinds never promote to height

    def test_directory_without_meta_is_inferred(self, tmp_path: Path):
        np.save(tmp_path / "topo.npy", np.zeros((4, 4)))
        ds = NpyLoader().load(tmp_path)
        assert ds.metadata["semantics"] == "inferred"
        assert ds.spacing == (1.0, 1.0)
        assert ds.get_channel("topo").kind == KIND_ELEVATION


@pytest.mark.usefixtures("qapp")
class TestNewViews:
    def _dataset(self, tmp_path: Path):
        TestMetaLoader()._write_run(tmp_path)
        return NpyLoader().load(tmp_path)

    def test_map_view_drainage(self, tmp_path: Path):
        from lem_viewer.views.map_2d import Map2DView

        ds = self._dataset(tmp_path)
        w = Map2DView().create_widget(ds, channel_name="drainage_area", levels=8, palette="fem")
        assert w.scale.levels == 8
        assert w.legend.edge_labels()[0].endswith("m2")
        hit = w.value_at(0.5, 0.5)  # km, inside the first cell
        assert hit is not None and hit[1] == pytest.approx(1e6, rel=1e-6)
        assert w.value_at(1e6, 1e6) is None

    def test_surface_view_drapes_colour_over_elevation(self, tmp_path: Path):
        from lem_viewer.views.surface_3d import Surface3DView, build_surface

        ds = self._dataset(tmp_path)
        _surface, scale, extents, color_ch, height_ch, vex = build_surface(ds, "drainage_area", levels=6)
        assert color_ch.name == "drainage_area" and height_ch.name == "elevation"
        # auto: relief (100 m) is scaled to 15% of the 3000 m extent
        assert vex == pytest.approx(0.15 * 3000.0 / 100.0)
        assert extents[0] == pytest.approx(3000.0) and extents[2] == pytest.approx(450.0)
        assert scale.levels == 6
        widget = Surface3DView().create_widget(ds, channel_name="drainage_area", vertical_exaggeration=3.0)
        assert widget.vertical_exaggeration == 3.0
        assert hasattr(widget, "gl_view") and hasattr(widget, "legend")

    def test_surface_vertex_colors_index_by_faces(self, tmp_path: Path):
        """Regression: colours must be flat (N*M, 4); (N, M, 4) raised IndexError inside paint()."""
        from lem_viewer.views.surface_3d import build_surface

        ds = self._dataset(tmp_path)
        surface, _scale, _ext, _c, _h, _vex = build_surface(ds, "drainage_area", levels=6)
        md = surface._meshdata
        n_vertices = ds.grid_shape[0] * ds.grid_shape[1]
        assert md.vertexColors().shape == (n_vertices, 4)
        by_faces = md.vertexColors(indexed="faces")  # this is what GLMeshItem.parseMeshData calls
        assert by_faces.shape == (md.faces().shape[0], 3, 4)

    def test_legacy_single_channel_uses_itself_as_height(self, tmp_path: Path):
        from lem_viewer.views.surface_3d import build_surface

        f = tmp_path / "sediment.npy"
        np.save(f, np.arange(16, dtype=float).reshape(4, 4))
        ds = NpyLoader().load(f)
        _s, _scale, extents, _c, height_ch, vex = build_surface(ds, "sediment")
        assert height_ch.name == "sediment"
        assert vex == pytest.approx(0.15 * 3.0 / 15.0)  # relief 15 on a 3-unit-wide grid is compressed
        assert extents[2] == pytest.approx(0.45)

    def test_single_file_in_run_directory_opens_whole_run(self, tmp_path: Path):
        """Opening elevation.npy next to meta.json must bring spacing and the other channels along."""
        from lem_viewer.ui.main_window import MainWindow
        from lem_viewer.views.surface_3d import build_surface

        TestMetaLoader()._write_run(tmp_path)
        ds = NpyLoader().load(tmp_path / "drainage_area.npy")
        assert ds.spacing == (1000.0, 1000.0)
        assert set(ds.channel_names) >= {"elevation", "drainage_area"}
        assert ds.metadata["primary_channel"] == "drainage_area"
        _s, _scale, extents, color_ch, height_ch, vex = build_surface(ds, "drainage_area")
        assert color_ch.name == "drainage_area" and height_ch.name == "elevation"
        assert extents[2] == pytest.approx(0.15 * 3000.0)  # relief scaled to 15% of the extent
        window = MainWindow()
        window.set_dataset(ds)
        assert window.primary_channel == "drainage_area"

    def test_auto_exaggeration_is_units_agnostic(self):
        from lem_viewer.views.surface_3d import auto_vertical_exaggeration

        assert auto_vertical_exaggeration(499_000.0, 6079.0) == pytest.approx(12.31, rel=1e-3)
        assert auto_vertical_exaggeration(499.0, 50.0) == pytest.approx(1.497, rel=1e-3)
        assert auto_vertical_exaggeration(499.0, 0.0) == 1.0

    def test_main_window_switches_to_map(self, tmp_path: Path):
        from lem_viewer.ui.main_window import MainWindow
        from lem_viewer.views.map_2d import Map2DWidget

        ds = self._dataset(tmp_path)
        window = MainWindow()
        window.set_dataset(ds)
        window._control_panel.set_view_mode("map_2d")
        assert window._control_panel.view_mode == "map_2d"
        assert isinstance(window._current_view, Map2DWidget)
        assert window._control_panel.palette == "fem" and window._control_panel.levels == 12
        assert window._control_panel.vertical_exaggeration is None
