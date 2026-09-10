"""Sampling helpers for the generator.

Rules recorded on 2026-09-09 (``current.md`` T-010): values with a sourced range are drawn uniformly when the range
spans less than one order of magnitude and log-uniformly otherwise; empirical distributions delivered as quantile
tables are sampled by inverse interpolation of the quantile points. All draws take an explicit ``numpy.random.Generator``
so that a sample is reproducible from its seed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

QUANTILE_KEYS = ("minimum", "p05", "p25", "median", "p75", "p95", "maximum")
QUANTILE_LEVELS = (0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0)


def spans_order_of_magnitude(lo: float, hi: float) -> bool:
    """True when ``hi / lo`` is at least 10 (both positive)."""
    return lo > 0 and hi > 0 and hi / lo >= 10.0


def sample_range(rng: np.random.Generator, lo: float, hi: float, size=None, *, force: str | None = None) -> np.ndarray | float:
    """Uniform or log-uniform draw in ``[lo, hi]`` following the 2026-09-09 rule (``force`` = 'uniform'|'log')."""
    lo, hi = float(lo), float(hi)
    if hi < lo:
        lo, hi = hi, lo
    mode = force or ("log" if spans_order_of_magnitude(lo, hi) else "uniform")
    if mode == "log":
        return np.exp(rng.uniform(np.log(lo), np.log(hi), size=size))
    return rng.uniform(lo, hi, size=size)


@dataclass(frozen=True)
class QuantileTable:
    """A distribution known through a few quantile points (as delivered by the data sessions)."""

    levels: tuple[float, ...]
    values: tuple[float, ...]
    n: int | None = None
    label: str = ""

    @classmethod
    def from_row(cls, row: dict, label: str = "", keys: Sequence[str] = QUANTILE_KEYS, levels: Sequence[float] = QUANTILE_LEVELS) -> "QuantileTable":
        lv, va = [], []
        for k, q in zip(keys, levels):
            v = row.get(k, "")
            if v in ("", None):
                continue
            lv.append(float(q))
            va.append(float(v))
        if len(va) < 2:
            raise ValueError(f"quantile row for {label!r} has fewer than two points")
        order = np.argsort(lv)
        n = row.get("n")
        return cls(tuple(np.asarray(lv)[order]), tuple(np.maximum.accumulate(np.asarray(va)[order])), int(float(n)) if n not in ("", None) else None, label)

    def sample(self, rng: np.random.Generator, size=None) -> np.ndarray | float:
        u = rng.uniform(self.levels[0], self.levels[-1], size=size)
        return np.interp(u, self.levels, self.values)

    def quantile(self, q: float) -> float:
        return float(np.interp(q, self.levels, self.values))


def sample_empirical(rng: np.random.Generator, values: Sequence[float], size=None) -> np.ndarray | float:
    """Draw with replacement from observed values (one record, one weight)."""
    arr = np.asarray(list(values), dtype=float)
    return rng.choice(arr, size=size, replace=True)


def sample_categorical(rng: np.random.Generator, labels: Sequence[str], probabilities: Sequence[float], size=None):
    p = np.asarray(probabilities, dtype=float)
    p = p / p.sum()
    return rng.choice(np.asarray(labels, dtype=object), size=size, p=p)


def sample_count_from_frequency(rng: np.random.Generator, counts: Sequence[int], landmass_counts: Sequence[int],
                                minimum: int = 0, maximum: int | None = None) -> int:
    """Draw an integer from an empirical count frequency table, then clip to ``[minimum, maximum]``."""
    c = np.asarray(counts, dtype=int)
    w = np.asarray(landmass_counts, dtype=float)
    v = int(rng.choice(c, p=w / w.sum()))
    if maximum is not None:
        v = min(v, int(maximum))
    return max(v, int(minimum))
