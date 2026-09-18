"""Data-derived figures only; the primary mask PNG is a lossless two-colour map."""
from pathlib import Path
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

OCEAN = (22, 41, 64)
PLATFORM = (220, 230, 211)
PAPER = (246, 247, 250)
INK = (27, 39, 53)


def font(size: int):
    for candidate in (Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/arial.ttf"),
                      Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")):
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default(size=size)


def mask_image(mask: np.ndarray) -> Image.Image:
    # PNG top row corresponds to the highest y, preserving Cartesian orientation.
    palette = np.asarray([OCEAN, PLATFORM], dtype=np.uint8)
    return Image.fromarray(palette[np.flipud(mask.astype(bool)).astype(np.uint8)])


def save_mask_png(path: Path, mask: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    mask_image(mask).save(path, format="PNG")


def decode_mask_png(path: Path) -> np.ndarray:
    pixels = np.asarray(Image.open(path).convert("RGB"))
    land = np.all(pixels == PLATFORM, axis=2)
    sea = np.all(pixels == OCEAN, axis=2)
    if not np.all(land | sea):
        raise ValueError("mask PNG contains colours outside the fixed two-colour palette")
    return np.flipud(land).copy()


def scalar_png(path: Path, values: np.ndarray, kind: str):
    from matplotlib import colormaps
    if kind == "noise":
        lo, hi, cmap = -3.0, 3.0, "RdBu_r"
    elif kind == "combined":
        lo, hi, cmap = -0.25, 1.25, "viridis"
    else:
        lo, hi, cmap = 0.0, 1.0, "viridis"
    colors = colormaps[cmap](np.clip((np.flipud(values)-lo)/(hi-lo), 0, 1), bytes=True)[:, :, :3]
    Image.fromarray(colors).save(path, format="PNG")


def contour_png(path: Path, mask: np.ndarray, contours: dict):
    image = mask_image(mask)
    draw = ImageDraw.Draw(image)
    height = mask.shape[0]
    for component in contours["components"]:
        for ring, color in [(component["outer"], (253, 176, 69)),
                            *[(hole, (247, 102, 128)) for hole in component["holes"]]]:
            points = [(x/contours["cell_km"], height-y/contours["cell_km"]) for x, y in ring]
            draw.line(points, fill=color, width=1)
    image.save(path, format="PNG")


def reference_atlas(path: Path, panels: list[tuple], title: str):
    columns, tile, label_h, margin = 6, 224, 35, 16
    rows = math.ceil(len(panels)/columns)
    canvas = Image.new("RGB", (columns*(tile+margin)+margin, 82+rows*(tile+label_h+margin)), PAPER)
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 15), title, fill=INK, font=font(23))
    draw.text((margin, 49), "Platform / outer footprint: light; surrounding water: dark", fill=INK, font=font(15))
    for i, (label, mask) in enumerate(panels):
        row, col = divmod(i, columns)
        x, y = margin+col*(tile+margin), 82+row*(tile+label_h+margin)
        panel = mask_image(mask)
        panel.thumbnail((tile, tile), Image.Resampling.NEAREST)
        canvas.paste(panel, (x+(tile-panel.width)//2, y+(tile-panel.height)//2))
        draw.text((x, y+tile+5), label, fill=INK, font=font(14))
    canvas.save(path, format="PNG")


def comparison_png(output: Path, samples: list[dict]):
    tile, margin, gap, header, label_h = 500, 32, 30, 138, 72
    rows = len(samples)//2
    canvas = Image.new("RGB", (margin*2+tile*2+gap, header+rows*(tile+label_h)+margin), PAPER)
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 16), "水下台地二维区域掩膜：六组配对", fill=INK, font=font(28))
    draw.text((margin, 57), "500 × 500 km · 1 km/格 · 浅色为台地区域 · 外圈 10 km 为海洋", fill=INK, font=font(18))
    for col, label in enumerate(("A  椭圆包络＋随机场", "B  参考形状叠加＋随机场")):
        draw.text((margin+col*(tile+gap), 99), label, fill=INK, font=font(23))
    for i, sample in enumerate(samples):
        row, col = divmod(i, 2)
        x, y = margin+col*(tile+gap), header+row*(tile+label_h)
        with Image.open(output / sample["relative_path"] / "mask.png") as source:
            canvas.paste(source, (x, y))
        m = sample["metrics"]
        draw.text((x, y+tile+8), f"种子 {sample['seed']}    占比 {m['fraction']:.4%}", fill=INK, font=font(20))
        longest = max(m["longest_straight_band_contact_km"].values())
        draw.text((x, y+tile+39), f"连通块 {m['components_4']}  |  边带最长连续接触 {longest} km", fill=INK, font=font(16))
    canvas.save(output / "comparison.png", format="PNG")


def calibration_png(path: Path, calibration: dict):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from .config import GAINS, STRETCHES
    values = np.asarray([c["loss"] for c in calibration["candidates"]]).reshape(len(STRETCHES), len(GAINS))
    fig, ax = plt.subplots(figsize=(7.3, 5.0), layout="constrained")
    image = ax.imshow(values, cmap="viridis_r", aspect="auto")
    ax.set_xticks(range(len(GAINS)), GAINS)
    ax.set_yticks(range(len(STRETCHES)), STRETCHES)
    ax.set_xlabel("Common noise gain")
    ax.set_ylabel("Ellipse log-axis-ratio multiplier")
    ax.set_title("Method A: 20 fixed candidates, 64 common seeds")
    for (row, col), value in np.ndenumerate(values):
        ax.text(col, row, f"{value:.3f}", ha="center", va="center", color="black",
                bbox={"facecolor": "white", "alpha": .75, "edgecolor": "none", "pad": 2})
    best = calibration["selected"]
    ax.plot(list(GAINS).index(best["gain"]), list(STRETCHES).index(best["stretch"]),
            "s", markersize=51, fillstyle="none", markeredgecolor="red", markeredgewidth=2)
    fig.colorbar(image, ax=ax, label="Sum of normalized Wasserstein distances")
    fig.savefig(path, dpi=170)
    plt.close(fig)


def statistics_png(path: Path, reference_model: dict, calibration: dict, calibration_rows: list[dict], samples: list[dict]):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from .reference import expected_log_metric
    selected = calibration["selected"]
    rows = [r for r in calibration_rows if float(r["stretch"]) == selected["stretch"] and float(r["gain"]) == selected["gain"]]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
    for ax, key, label in zip(axes, ("axis_ratio", "shoreline_development"), ("PCA axis ratio", "Crofton shoreline development")):
        sources = [("Reference (34)", reference_model["metrics"][key]["residuals"], "#222222"),
                   ("A calibration (64)", [np.log(float(r[key]))-expected_log_metric(reference_model, key, float(r["area_km2"])) for r in rows], "#c75b16")]
        for method, color in (("ellipse", "#e79444"), ("reference_overlay", "#006ba4")):
            own = [s["metrics"] for s in samples if s["method"] == method]
            sources.append(("A final (6)" if method == "ellipse" else "B final (6), diagnostic only",
                            [np.log(m[key])-expected_log_metric(reference_model, key, m["area_km2"]) for m in own], color))
        for name, data, color in sources:
            sorted_data = np.sort(data)
            ax.step(sorted_data, np.arange(1, len(data)+1)/len(data), where="post", label=name, color=color)
        ax.set_title(label)
        ax.set_xlabel("log(metric) minus fitted log-area expectation")
        ax.set_ylabel("Empirical cumulative fraction")
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
    fig.savefig(path, dpi=170)
    plt.close(fig)
