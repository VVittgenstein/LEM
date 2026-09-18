"""Sea-level schedule SL(t): real curves, long-term plus short-term (yZz 2026-09-08).

* Long-term: Miller et al. 2020 smoothed series (session A, ``sea-level-miller-smoothed-series.json``, ages 0.98 to
  64.8 Myr BP, 20 kyr spacing). A window of length T is cut at a random start age inside 0.98 to 48 Myr (the range
  used by A's statistics) and the value at the window start is subtracted so that SL(0) = 0.
* Short-term: Spratt & Lisiecki 2016 series (``sea-level-spratt-series.json``, 0 to 798 kyr BP, 1 kyr spacing),
  cycled with a random start and its own mean removed before addition (yZz 2026-09-08). Cycling is done by
  reflection at the series ends so that no jump of about 100 m appears at the wrap (Claude, assumption).
* Time runs forward in the model, so ages decrease with model time.

The initial bathymetry is written relative to SL(0) = 0; the schedule only moves the sea level afterwards.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict

import numpy as np

from .paths import A_TABLES

MILLER_MIN_AGE_YR = 0.98e6
MILLER_MAX_AGE_YR = 48.0e6


def _load_series(name: str) -> tuple[np.ndarray, np.ndarray]:
    rows = json.loads((A_TABLES / name).read_text(encoding="utf-8"))
    age = np.asarray([r["age_yr_bp"] for r in rows], dtype=float)
    sl = np.asarray([r["sea_level_m"] for r in rows], dtype=float)
    order = np.argsort(age)
    return age[order], sl[order]


@dataclass
class SeaLevelParams:
    t_end_yr: float
    long_start_age_yr: float
    short_start_age_yr: float
    short_direction: int  # +1: model time moves to younger ages first; -1: to older ages first
    use_long: bool = True
    use_short: bool = True
    evidence_state: str = "来源直接给出（曲线）；循环与去均值为本项目改造"


class SeaLevelSchedule:
    def __init__(self, params: SeaLevelParams):
        self.p = params
        self.miller_age, self.miller_sl = _load_series("sea-level-miller-smoothed-series.json")
        self.spratt_age, self.spratt_sl = _load_series("sea-level-spratt-series.json")
        self.spratt_mean = float(self.spratt_sl.mean())
        self.spratt_span = float(self.spratt_age[-1] - self.spratt_age[0])
        self._short0 = self._short_raw(0.0)
        self._long0 = self._long_raw(0.0)

    @classmethod
    def sample(cls, rng: np.random.Generator, t_end_yr: float, use_long: bool = True, use_short: bool = True) -> "SeaLevelSchedule":
        lo = MILLER_MIN_AGE_YR + t_end_yr
        hi = MILLER_MAX_AGE_YR
        if lo >= hi:
            raise ValueError(f"T = {t_end_yr:g} yr exceeds the usable Miller window")
        long_start = float(rng.uniform(lo, hi))
        short_start = float(rng.uniform(0.0, 798e3))
        direction = int(rng.choice([-1, 1]))
        return cls(SeaLevelParams(t_end_yr=float(t_end_yr), long_start_age_yr=long_start, short_start_age_yr=short_start,
                                  short_direction=direction, use_long=use_long, use_short=use_short))

    def _long_raw(self, t: float) -> float:
        age = self.p.long_start_age_yr - t
        return float(np.interp(age, self.miller_age, self.miller_sl))

    def _short_raw(self, t: float) -> float:
        # reflected (ping-pong) cycling over the 0..798 kyr series
        a = self.p.short_start_age_yr + self.p.short_direction * t
        period = 2.0 * self.spratt_span
        a = np.mod(a - self.spratt_age[0], period)
        a = np.where(a > self.spratt_span, period - a, a) + self.spratt_age[0]
        return float(np.interp(a, self.spratt_age, self.spratt_sl)) - self.spratt_mean

    def __call__(self, t: float) -> float:
        sl = 0.0
        if self.p.use_long:
            sl += self._long_raw(t) - self._long0
        if self.p.use_short:
            sl += self._short_raw(t) - self._short0
        return sl

    def series(self, dt: float) -> np.ndarray:
        ts = np.arange(0.0, self.p.t_end_yr + dt, dt)
        return np.asarray([self(t) for t in ts])

    def describe(self) -> dict:
        d = asdict(self.p)
        s = self.series(10e3)
        d.update({"min_m": float(s.min()), "max_m": float(s.max()), "final_m": float(s[-1]),
                  "sources": ["Miller et al. 2020 smoothed (session A)", "Spratt and Lisiecki 2016 (session A)"]})
        return d
