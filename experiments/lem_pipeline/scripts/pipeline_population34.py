"""Re-aggregate the class-1 (session A) and class-4 (session D) statistics for the 34-landmass reference population.

Writes docs/work/2026-09-08-q1-data/merged/data-package/pop34/ with CSV tables, a README and a manifest.

Run with the lem-env interpreter: PYTHONPATH=experiments lem-env/python.exe experiments/lem_pipeline/scripts/pipeline_population34.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file()) / "experiments"))

from lem_pipeline import reference as ref  # noqa: E402
from lem_pipeline.paths import POP34_PACKAGE  # noqa: E402


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    all_rows, ids = ref.population_ids(60.0)
    assert len(ids) == 34, len(ids)
    landmasses = ref.load_a_landmasses(ids)
    out = POP34_PACKAGE
    out.mkdir(parents=True, exist_ok=True)
    members = [{"id": i, "name": all_rows[i]["name"], "latitude": all_rows[i]["latitude"], "longitude": all_rows[i]["longitude"],
                "land_area_km2": all_rows[i]["land_area_km2"], "in_A_spatial_tables": i in landmasses} for i in ids]
    ref.write_csv(out / "population-members.csv", members)
    c1 = ref.aggregate_class1(landmasses)
    ref.write_csv(out / "class1-depth-roughness-land-pop34.csv", c1)
    c4, emb = ref.aggregate_class4(ids)
    ref.write_csv(out / "class4-shape-statistics-pop34.csv", c4)
    ref.write_csv(out / "class4-inner-sea-proxy-pop34.csv", emb)
    readme = f"""# 参考总体 34 个陆块的重汇总

日期：{datetime.now(timezone.utc).strftime('%Y-%m-%d')}。生成脚本：`experiments/lem_pipeline/scripts/pipeline_population34.py`（`experiments/lem_pipeline/reference.py`）。总体：D 会话核定的 71 个大陆地壳型陆块中 `abs(latitude) < 60` 的 34 个（yZz 2026-09-09 决定）。输入为 A 会话的逐陆块 JSON（`A-initial-elevation-sealevel/tables/spatial-by-landmass/`，{len(landmasses)} 个陆块有文件）与 D 会话的逐陆块表。全部行的依据状态为“本项目借鉴或合成改造”；本重汇总不构成验收。

| 文件 | 内容 |
|---|---|
| `population-members.csv` | 34 个成员及其是否有 A 的逐陆块文件 |
| `class1-depth-roughness-land-pop34.csv` | 各子类、各离岸带的逐陆块中位水深分布与像元合并分位数；陆架几何；海底起伏；陆地高程分位数分布与像元合并 |
| `class4-shape-statistics-pop34.csv` | 形状统计量的全体与面积三分组分位数、与面积的秩相关、放大后可达占比的形状数 |
| `class4-inner-sea-proxy-pop34.csv` | 内海代理有候选的陆块比例 |

150 km 口径的周边分类、连续段、陆架剖面与陆缘标签以 F 会话的交付为准（`docs/work/2026-09-09-q1-pretasks/`），本包只覆盖 A 与 D 的量。
"""
    (out / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    files = [{"path": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)} for p in sorted(out.iterdir()) if p.is_file() and p.name != "manifest.json"]
    (out / "manifest.json").write_text(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(), "population": 34,
                                                   "members": ids, "files": files}, indent=1, ensure_ascii=False), encoding="utf-8")
    print("written", out, "| landmasses with A tables:", len(landmasses), "| class1 rows:", len(c1), "| class4 rows:", len(c4), "| inner-sea rows:", len(emb))


if __name__ == "__main__":
    main()
