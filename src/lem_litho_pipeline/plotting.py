import numpy as np
from .diagnostics import coastline_mask, terrain_derivatives


def _terrain_panel(ax, elevation, dx, title):
    derivatives = terrain_derivatives(elevation, dx)
    image = ax.imshow(elevation, origin="lower", cmap="terrain")
    ax.imshow(derivatives["hillshade"], origin="lower", cmap="gray", alpha=0.30,
              vmin=0, vmax=1)
    coast = coastline_mask(elevation)
    if np.any(coast):
        ax.contour(coast.astype(float), levels=[0.5], colors="cyan", linewidths=0.7,
                   origin="lower")
    ax.set_title(title + "; cyan coastline")
    return image


def _show(fig, ax, data, title, cmap, **kwargs):
    image = ax.imshow(data, origin="lower", cmap=cmap, **kwargs)
    ax.set_title(title)
    fig.colorbar(image, ax=ax, shrink=0.82)


def plot_inputs(path, config, inputs):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 3, figsize=(16, 9), constrained_layout=True)
    image = _terrain_panel(axes[0, 0], inputs.elevation, config.dx,
                           "Initial elevation and hillshade (m)")
    fig.colorbar(image, ax=axes[0, 0], shrink=0.82)
    _show(fig, axes[0, 1], inputs.uplift * 1000, "Continuous uplift and ridge network (mm/yr)", "magma")
    if inputs.ridge_field is not None:
        axes[0, 1].contour(inputs.ridge_field, levels=[0.35, 0.65], colors=["cyan", "white"],
                           linewidths=[0.5, 0.8], origin="lower")
    planned = np.ma.masked_where(~inputs.land_mask, inputs.landform)
    cmap = plt.get_cmap("tab10").copy()
    cmap.set_bad("#17486b")
    _show(fig, axes[0, 2], planned, "Dominant planned landform ID; ocean masked", cmap,
          vmin=0, vmax=4)
    _show(fig, axes[1, 0], inputs.province, "Dominant geological province ID", "tab10",
          vmin=0, vmax=3)
    _show(fig, axes[1, 1], inputs.labels[:, :, 0], "Initial surface lithology ID", "tab10",
          vmin=0, vmax=4)
    section = inputs.labels[config.ny // 2, :, :].T
    image = axes[1, 2].imshow(section, origin="upper", cmap="tab10", aspect="auto",
                              vmin=0, vmax=4,
                              extent=(0, config.length[1] / 1000, config.depth, 0))
    axes[1, 2].set_title("Central lithology section")
    axes[1, 2].set_xlabel("x (km)")
    axes[1, 2].set_ylabel("depth below initial surface (m)")
    fig.colorbar(image, ax=axes[1, 2], shrink=0.82)
    fig.suptitle("Planned landforms: " + ", ".join(inputs.planned_landforms), fontsize=12)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def terrain_3d_geometry(elevation, dx, stride):
    """Return decimated kilometre coordinates and physical spans for 3D plots."""
    surface = np.asarray(elevation, dtype=float)
    if surface.ndim != 2 or min(surface.shape) < 2 or not np.all(np.isfinite(surface)):
        raise ValueError("elevation must be a finite two-dimensional array")
    if not np.isfinite(dx) or dx <= 0 or stride < 1:
        raise ValueError("dx and stride must be positive")
    z_km = surface[::stride, ::stride] / 1000
    y_km = np.arange(0, surface.shape[0], stride) * dx / 1000
    x_km = np.arange(0, surface.shape[1], stride) * dx / 1000
    spans_km = ((surface.shape[1] - 1) * dx / 1000,
                (surface.shape[0] - 1) * dx / 1000,
                max(float(z_km.max() - z_km.min()), np.finfo(float).eps))
    return x_km, y_km, z_km, spans_km


def plot_terrain_3d(path, elevation, dx=100.0, title="Terrain surface"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource
    surface = np.asarray(elevation, dtype=float)
    stride = max(1, int(np.ceil(max(surface.shape) / 320)))
    x, y, z, spans_km = terrain_3d_geometry(surface, dx, stride)
    xx, yy = np.meshgrid(x, y)
    colors = LightSource(azdeg=315, altdeg=35).shade(z, cmap=plt.get_cmap("terrain"),
                                                     vert_exag=0.7, blend_mode="soft")
    fig = plt.figure(figsize=(13, 10), constrained_layout=True)
    ax = fig.add_subplot(111, projection="3d")
    ax.plot_surface(xx, yy, z, facecolors=colors, rstride=1, cstride=1,
                    linewidth=0, antialiased=False, shade=False)
    ax.contour(xx, yy, z, levels=[0.0], colors="cyan", linewidths=1.0, offset=float(z.min()))
    ax.set_title(title)
    ax.set_xlabel("x (km)")
    ax.set_ylabel("y (km)")
    ax.set_zlabel("elevation (km)")
    ax.view_init(elev=38, azim=-128)
    ax.set_xlim(0.0, spans_km[0])
    ax.set_ylim(0.0, spans_km[1])
    ax.set_zlim(float(z.min()), float(z.max()))
    ax.set_box_aspect(spans_km)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_outputs(path, fields, dx=100.0):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    derivatives = terrain_derivatives(fields["elevation"], dx)
    drainage = np.asarray(fields["drainage_area"])
    positive = drainage[drainage > 0]
    river_threshold = np.percentile(positive, 95) if positive.size else np.inf
    rivers = np.ma.masked_where(drainage < river_threshold, np.log10(1 + drainage))

    fig, axes = plt.subplots(2, 3, figsize=(16, 9), constrained_layout=True)
    image = _terrain_panel(axes[0, 0], fields["elevation"], dx, "Final elevation and hillshade (m)")
    if np.any(~rivers.mask):
        axes[0, 0].imshow(rivers, origin="lower", cmap="Blues", alpha=0.85)
    axes[0, 0].set_title("Final shaded relief, coastline and upper 5% drainage")
    fig.colorbar(image, ax=axes[0, 0], shrink=0.82)
    _show(fig, axes[0, 1], np.log10(1 + drainage), "Drainage: log10(1 + area / m²)", "Blues")
    _show(fig, axes[0, 2], derivatives["slope"], "Slope (m/m)", "inferno")
    _show(fig, axes[1, 0], derivatives["local_relief"], "Local relief (m)", "viridis")
    _show(fig, axes[1, 1], fields["erosion_rate"],
          "Last interval net erosion (m/yr)", "coolwarm")
    _show(fig, axes[1, 2], fields["exposed_lithology"],
          "Final voxel intercept lithology ID", "tab10", vmin=0, vmax=4)
    fig.savefig(path, dpi=140)
    plt.close(fig)
