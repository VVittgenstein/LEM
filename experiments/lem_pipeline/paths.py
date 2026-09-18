"""Repository-relative locations used by the pipeline.

Data deliveries live under ``docs/work`` (tracked on the private branch), reference acquisitions under ``references/data``
(git-ignored), generated samples under ``output`` (git-ignored). Override the root with ``LEM_ROOT`` when the
package is used outside the repository checkout.
"""
from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("LEM_ROOT")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "AGENTS.md").exists() and (parent / "final-strategy").is_dir():
            return parent
    raise RuntimeError("Project root unavailable; set LEM_ROOT explicitly")


ROOT = repo_root()
Q1_DATA = ROOT / "docs" / "work" / "2026-09-08-q1-data"
PRETASKS = ROOT / "docs" / "work" / "2026-09-09-q1-pretasks"
A_TABLES = Q1_DATA / "A-initial-elevation-sealevel" / "tables"
D_TABLES = Q1_DATA / "D-landform-statistics" / "tables"
MERGED_Q1 = Q1_DATA / "merged"
MERGED_PRETASKS = PRETASKS / "merged"
POP34_PACKAGE = MERGED_Q1 / "data-package" / "pop34"
REFERENCE_DATA = ROOT / "references" / "data"
OUTPUT = ROOT / "output"
