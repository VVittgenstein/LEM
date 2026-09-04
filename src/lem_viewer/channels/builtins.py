"""Built-in derived-channel providers: slope and hillshade."""

from __future__ import annotations

import numpy as np

from lem_viewer.channels.base import ChannelProvider
from lem_viewer.models import DisplayDefaults, TerrainChannel, TerrainDataset
from lem_viewer.registry import registry
from lem_viewer.semantics import find_elevation_channel


@registry.channel_provider("slope")
class SlopeProvider(ChannelProvider):
    """Compute slope magnitude from an elevation channel."""

    def can_provide(self, dataset: TerrainDataset) -> bool:
        return find_elevation_channel(dataset) is not None

    def provide(self, dataset: TerrainDataset) -> list[TerrainChannel]:
        elev = find_elevation_channel(dataset).get_array()
        dy, dx = dataset.spacing
        grad_y, grad_x = np.gradient(elev, dy, dx)
        slope = np.sqrt(grad_x**2 + grad_y**2)
        ch = TerrainChannel(
            name="slope",
            units="m/m",
            array=slope,
            display_defaults=DisplayDefaults(colormap="viridis"),
        )
        ch.compute_stats()
        return [ch]


@registry.channel_provider("hillshade")
class HillshadeProvider(ChannelProvider):
    """Compute hillshade from an elevation channel."""

    # Default illumination parameters (degrees).
    azimuth_deg: float = 315.0
    altitude_deg: float = 45.0

    def can_provide(self, dataset: TerrainDataset) -> bool:
        return find_elevation_channel(dataset) is not None

    def provide(self, dataset: TerrainDataset) -> list[TerrainChannel]:
        elev = find_elevation_channel(dataset).get_array()
        dy, dx = dataset.spacing
        grad_y, grad_x = np.gradient(elev, dy, dx)

        azimuth = np.radians(self.azimuth_deg)
        altitude = np.radians(self.altitude_deg)

        slope = np.arctan(np.sqrt(grad_x**2 + grad_y**2))
        aspect = np.arctan2(-grad_y, grad_x)

        hillshade = np.sin(altitude) * np.cos(slope) + np.cos(altitude) * np.sin(
            slope
        ) * np.cos(azimuth - aspect)
        hillshade = np.clip(hillshade, 0.0, 1.0)

        ch = TerrainChannel(
            name="hillshade",
            units="",
            array=hillshade,
            display_defaults=DisplayDefaults(colormap="gray", vmin=0.0, vmax=1.0),
        )
        ch.compute_stats()
        return [ch]
