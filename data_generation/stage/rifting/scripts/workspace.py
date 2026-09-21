"""Paths and provenance for the authorized rifting evidence review."""
from __future__ import annotations
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

def canonical(path):
    value = str(Path(path).resolve())
    if value.startswith('\\\\?\\UNC\\'):
        value = '\\\\' + value[8:]
    elif value.startswith('\\\\?\\'):
        value = value[4:]
    return Path(value)

ROOT = canonical(__file__).parents[1]
PROJECT = ROOT.parents[2]

def target(relative):
    path = canonical(ROOT / relative)
    if path != ROOT and ROOT not in path.parents:
        raise ValueError(f"Output outside rifting workspace: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_json(relative, value):
    path = target(relative)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return path

def read_csv(path, **kwargs):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, **kwargs))

def write_csv(relative, rows):
    path = target(relative)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path

def utc_now():
    return datetime.now(timezone.utc).isoformat()
