"""Headless diagnostic plots; matplotlib is imported only when requested."""
import numpy as np


def plot_inputs(path, config, inputs):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
    panels = [
        (inputs.elevation, "Initial elevation (m)", "terrain"),
        (inputs.uplift, "Uplift (m/yr)", "viridis"),
        (inputs.province, "Geological province ID", "tab10"),
        (inputs.labels[:, :, 0], "Initial surface material ID", "tab10"),
        (inputs.labels[config.ny // 2, :, :].T, "Central y section: depth index vs x", "tab10"),
        (inputs.labels[:, config.nx // 2, :].T, "Central x section: depth index vs y", "tab10"),
    ]
    for ax, (data, title, cmap) in zip(axes.flat, panels):
        image = ax.imshow(data, origin="upper" if "section" in title else "lower", cmap=cmap,
                          aspect="auto", **({"vmin": 0, "vmax": 4} if cmap == "tab10" else {}))
        ax.set_title(title)
        fig.colorbar(image, ax=ax)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_outputs(path, fields):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), constrained_layout=True)
    panels = [(fields["elevation"], "Elevation (m)", "terrain"),
              (np.log10(1 + fields["drainage_area"]), "log10(1 + area / m²)", "viridis"),
              (fields["erosion_rate"], "Last-interval net erosion (m/yr), positive lowering", "coolwarm"),
              (fields["exposed_lithology"], "Final voxel-intercept material ID", "tab10")]
    for ax, (data, title, cmap) in zip(axes.flat, panels):
        image = ax.imshow(data, origin="lower", cmap=cmap)
        ax.set_title(title)
        fig.colorbar(image, ax=ax)
    fig.savefig(path, dpi=130)
    plt.close(fig)
