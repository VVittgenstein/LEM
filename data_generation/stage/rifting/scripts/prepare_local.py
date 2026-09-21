"""Freeze selected existing evidence without changing its original location."""
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path
from workspace import PROJECT, ROOT, digest, target, utc_now, write_json

PACKAGE = PROJECT / "references/2026-09-13-geological-activity-parameters"
FILES = [
    "README.md", "METHOD.md", "GAPS.md", "TWO_GOAL_EVIDENCE.md", "records/rift.md",
    "tables/source_register.csv", "tables/activity_records.csv", "tables/literature_quantities.csv",
    "tables/T01_rift_catalogue.csv", "tables/R05_growth_strata_fault_rates.csv",
    "tables/R01_Basement_Lake_Turkana.csv", "tables/R01_Gombe_Lake_Turkana.csv",
    "tables/B07_backstripping_profile_rates.csv", "tables/timing_evidence.csv",
    "sources/T01/41561_2017_3_MOESM2_ESM.csv", "sources/T01/rifts_of_the_world_2001.txt",
    "sources/S01/gem_active_faults_harmonized.geojson", "sources/S01/README.md",
    "sources/S01/LICENSE.txt", "sources/S01/github_commit.json",
    "sources/R01/article.txt", "sources/R02/article.txt",
    "checks/source_views/T01_methods.png", "checks/source_views/T01_table_header_reading.png",
]

def main():
    records = []
    for rel in FILES:
        source = PACKAGE / rel
        dest = target("sources/existing/" + rel)
        shutil.copyfile(source, dest)
        original_hash, frozen_hash = digest(source), digest(dest)
        assert original_hash == frozen_hash
        records.append(dict(original=str(source), frozen=dest.relative_to(ROOT).as_posix(),
                            bytes=dest.stat().st_size, sha256=frozen_hash))
    source = Path("C:/Users/YZZ/Desktop/Downloads/LEM_rifting_design_v0.1.md")
    dest = target("sources/design/LEM_rifting_design_v0.1.md")
    shutil.copyfile(source, dest)
    records.append(dict(original=str(source), frozen=dest.relative_to(ROOT).as_posix(),
                        bytes=dest.stat().st_size, sha256=digest(dest)))
    write_json("output/checks/local_source_manifest.json", dict(created_utc=utc_now(), files=records))
    baseline = dict(created_utc=utc_now(),
                    head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip(),
                    status=subprocess.check_output(["git", "status", "--short"], cwd=PROJECT, text=True),
                    directory=str(ROOT))
    if not (ROOT / "output/checks/worktree_at_start.json").exists():
        write_json("output/checks/worktree_at_start.json", baseline)
    print(f"Copied and hash-checked {len(records)} local sources.")

if __name__ == "__main__":
    main()
