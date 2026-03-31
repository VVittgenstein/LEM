"""Side-by-side compare view with synchronised cameras."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter

from lem_viewer.models import TerrainDataset
from lem_viewer.registry import registry
from lem_viewer.views.base import ViewPlugin
from lem_viewer.views.surface_3d import Surface3DView, SyncableGLView


class CameraSync:
    """Bidirectional camera synchronisation between two :class:`SyncableGLView`."""

    def __init__(self, a: SyncableGLView, b: SyncableGLView) -> None:
        self._views = (a, b)
        a.camera_changed.connect(lambda: self._propagate(a, b))
        b.camera_changed.connect(lambda: self._propagate(b, a))

    def _propagate(self, src: SyncableGLView, dst: SyncableGLView) -> None:
        dst.apply_camera_state(src.camera_state())


class CompareWidget(QSplitter):
    """QSplitter holding two synced 3D views."""

    def __init__(
        self,
        left: SyncableGLView,
        right: SyncableGLView,
        parent: Any = None,
    ) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.addWidget(left)
        self.addWidget(right)
        self.left_view = left
        self.right_view = right
        self.camera_sync = CameraSync(left, right)


@registry.view("compare_surface_3d")
class CompareSurface3DView(ViewPlugin):
    """Two 3D surfaces shown side-by-side with synchronised cameras."""

    @property
    def display_name(self) -> str:
        return "Compare 3D Surfaces"

    def create_widget(
        self, dataset: TerrainDataset, **kwargs: Any
    ) -> CompareWidget:
        primary: str = kwargs.get(
            "primary_channel", dataset.channel_names[0]
        )
        secondary: str = kwargs.get(
            "secondary_channel", dataset.channel_names[0]
        )
        max_display_size: int = kwargs.get("max_display_size", 512)

        builder = Surface3DView()
        left = builder.create_widget(
            dataset, channel_name=primary, max_display_size=max_display_size
        )
        right = builder.create_widget(
            dataset, channel_name=secondary, max_display_size=max_display_size
        )

        return CompareWidget(left, right)
