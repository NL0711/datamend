"""Checks for temperature, pressure and relative humidity readings of a stream (slice S4), registered in the one check catalogue.

NEW code (not a revival of the legacy tiers): fixed rules and robust statistics on the station's own earlier readings. NOT a trained model.
Every threshold and weight below is an `assumed` design choice, uncalibrated; the evaluation of them is SYNTHETIC (tests/test_weather_eval.py).

Conventions follow validation/checks.py: each check declares what it needs (CATALOGUE); a check that cannot run for a reading is listed in
``not_run`` with the reason and is never scored; a hit carries evidence whose numbers are tagged measured, assumed or derived; the rule score
is 1 - prod(1 - weight) and never a probability; verdicts are OK, SUSPECT (a fault-kind check fired), UNCERTAIN, NO_DATA.

THE RULE: magnitude alone is never called a fault. An out-of-pattern value is a fault only when it is isolated (no other variable moves with it
in a physically consistent way). When two or more variables deviate together AND the dew point derived from temperature and humidity stays
about where it was (a squall front: temperature and pressure fall, humidity rises, the dew point holds), the deviation is a genuine-extreme
candidate: its hits are downgraded to UNCERTAIN and carry ``corroboration.coherent = true``. A value beyond the physical limits, a sentinel or
non-finite number, a frozen value and a lost variable are fault-kind.

PRESSURE ASSUMPTION: the value is STATION pressure (not reduced to sea level) from a station whose elevation is not part of the reading. The
hard limits 300 to 1100 hPa therefore cover stations from sea level to about 9 km; there is no absolute "extreme" band for pressure (it would
call a mountain station extreme all day). Sea-level pressure would sit inside the same limits, so the limits are safe for both; the own-history
checks do the real work.
"""
from __future__ import annotations

import math
import statistics
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Deque, Dict, List, Mapping, NamedTuple, Optional, Sequence, Tuple

from backend.app.validation import checks as cat
from backend.app.validation.checks import CheckHit, CheckSpec, _thr

METHOD = "rules + own-history robust statistics + dew-point consistency (not a trained model); weights and thresholds are design choices, not calibrated"
VARIABLES = ("temperature", "pressure", "humidity")
UNIT = {"temperature": "C", "pressure": "hPa", "humidity": "%"}

# ---- thresholds (all `assumed`: design choices, uncalibrated)
HARD_BOUNDS = {"temperature": (-90.0, 60.0),        # below the lowest and above the highest air temperature ever recorded (-89.2 and 56.7 C)
               "pressure": (300.0, 1100.0),         # station pressure, sea level to about 9 km; sea-level extremes (870 to 1085) lie inside
               "humidity": (0.0, 105.0)}            # 0 to 100 % plus 5 points of sensor overshoot
EXTREME_TEMPERATURE = (-50.0, 50.0)                 # inside the limits but rare enough that nobody confirms it: UNCERTAIN only
SENTINELS = (-999.0, -9999.0, 9999.0, 9999.9, 99999.0)
RATE_FLOOR = {"temperature": 2.0, "pressure": 1.5, "humidity": 8.0}      # allowed step between readings, even at zero elapsed time (sensor noise)
RATE_PER_MIN = {"temperature": 0.5, "pressure": 0.4, "humidity": 3.0}    # plus this much per minute between the two readings
MAX_GAP_MIN = 120.0                 # history older than this gap is not context: history-based checks do not run
FROZEN_N = 8                        # identical readings in a row (this one included)
FROZEN_MIN_SPAN_S = 120.0           # and they must span at least this long (a coarse sensor repeats a value for seconds)
SATURATED_RH = 99.9                # humidity at saturation can legitimately stay at 100 for hours: not a frozen sensor
SPIKE_WINDOW, SPIKE_MIN, LEVEL_N = 30, 10, 9
SPIKE_RECENT_SKIP = 24              # readings skipped when looking for the level before an episode (same span as SHIFT_RECENT_EXCLUDE)
SPIKE_K = 8.0                      # robust standard deviations of successive differences
SPIKE_SCALE_FLOOR = {"temperature": 0.2, "pressure": 0.15, "humidity": 0.8}
SPIKE_ABS = {"temperature": 3.0, "pressure": 2.5, "humidity": 12.0}      # a deviation smaller than this is never a spike
NATURAL_PER_MIN = {"temperature": 0.04, "pressure": 0.05, "humidity": 0.2}   # slowest-to-fastest natural drift allowed on top, per minute
CORROBORATION_FRACTION = 0.5        # another variable "moves with it" when it deviates by half its own spike limit
DEWPOINT_COHERENT_C = 6.0           # the dew point may differ this much from its recent level and still count as steady
SHIFT_N, SHIFT_RECENT_EXCLUDE = 80, 24      # baseline = the earlier readings before the last 24, so a slow ramp does not contaminate it
SHIFT_ABS = {"temperature": 1.5, "pressure": 1.5, "humidity": 8.0}
SHIFT_NATURAL_PER_MIN = {"temperature": 0.04, "pressure": 0.02, "humidity": 0.15}
DEWPOINT_STEP_C, DEWPOINT_PER_MIN = 3.0, 0.3
DEWPOINT_ABOVE_TEMPERATURE_C = 0.5
GAP_FACTOR, GAP_ABS_MIN_S, GAP_MIN_HISTORY = 5.0, 30.0, 6
DROPOUT_LOOKBACK = 30               # a variable counts as "reported by this station" when any of its last 30 readings had it
HISTORY_MAX = 96                    # readings kept per station (the longest check needs SHIFT_N = 80)
MAX_STATIONS = 5000                 # stations kept (oldest dropped): memory is bounded

MAGNUS_B, MAGNUS_C = 17.67, 243.5   # Magnus-Tetens, as the simulator's physics uses

CATALOGUE_SPECS = [
    CheckSpec("corrupt_value", "stream", "integrity", "fault", 0.90, "a value (non-finite or a sentinel such as 9999.9 or -999)"),
    CheckSpec("value_out_of_range", "stream", "rule", "fault", 0.90, "a value of temperature, pressure or humidity"),
    CheckSpec("extreme_value", "stream", "rule", "uncertain", 0.30, "a temperature value"),
    CheckSpec("rate_of_change", "stream", "rule", "uncertain", 0.30, "a previous reading of the variable within the context gap, and both timestamps"),
    CheckSpec("frozen_value", "stream", "rule", "fault", 0.60, f"{FROZEN_N} consecutive identical readings of the variable"),
    CheckSpec("spike_vs_history", "stream", "statistic", "fault", 0.60, f"{SPIKE_MIN} earlier readings of the variable (robust level and noise scale)"),
    CheckSpec("level_shift", "stream", "statistic", "uncertain", 0.30, f"{SHIFT_N} earlier readings of the variable"),
    CheckSpec("dewpoint_above_temperature", "stream", "consistency", "fault", 0.80, "temperature and humidity in the same reading"),
    CheckSpec("dewpoint_jump", "stream", "consistency", "uncertain", 0.35, "temperature and humidity in this and the previous reading"),
    CheckSpec("dropout", "stream", "integrity", "fault", 0.60, f"a variable missing now that this station reported in its last {DROPOUT_LOOKBACK} readings"),
    CheckSpec("reporting_gap", "stream", "integrity", "uncertain", 0.30, f"{GAP_MIN_HISTORY} earlier readings (to know the station's cadence)"),
]
for _spec in CATALOGUE_SPECS:
    cat.CATALOGUE[_spec.name] = _spec


# ------------------------------------------------------------------------------------------------ per-station rolling history
class ClimateSample(NamedTuple):
    timestamp: datetime
    temperature: Optional[float]
    pressure: Optional[float]
    humidity: Optional[float]


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _finite(x: Any) -> bool:
    return _is_num(x) and math.isfinite(x)


class ClimateHistory:
    """The last ``HISTORY_MAX`` readings of each station, oldest first, for the checks. Causal: a reading is added only after it was scored, and a
    reading not later than the newest one is ignored. Bounded: ``HISTORY_MAX`` per station and ``MAX_STATIONS`` stations."""

    def __init__(self, max_len: int = HISTORY_MAX, max_stations: int = MAX_STATIONS) -> None:
        self._max_len, self._max_stations = max_len, max_stations
        self._by_station: "OrderedDict[str, Deque[ClimateSample]]" = OrderedDict()

    def __contains__(self, station_id: str) -> bool:
        return station_id in self._by_station

    def __len__(self) -> int:
        return len(self._by_station)

    def recent(self, station_id: str) -> List[ClimateSample]:
        return list(self._by_station.get(station_id, ()))

    def seed(self, station_id: str, samples: Sequence[ClimateSample]) -> None:
        """Load earlier readings (from the database) once, oldest first."""
        d = self._by_station.setdefault(station_id, deque(maxlen=self._max_len))
        for s in sorted(samples, key=lambda s: s.timestamp):
            if not d or s.timestamp > d[-1].timestamp:
                d.append(s)
        self._trim()

    def add(self, station_id: str, sample: ClimateSample) -> None:
        d = self._by_station.setdefault(station_id, deque(maxlen=self._max_len))
        self._by_station.move_to_end(station_id)
        if not d or sample.timestamp > d[-1].timestamp:
            d.append(sample)
        self._trim()

    def _trim(self) -> None:
        while len(self._by_station) > self._max_stations:
            self._by_station.popitem(last=False)


# ------------------------------------------------------------------------------------------------ helpers
@dataclass
class WeatherResult:
    hits: List[CheckHit] = field(default_factory=list)
    not_run: List[Dict[str, str]] = field(default_factory=list)
    has_data: bool = False                # at least one of temperature, pressure, humidity was reported at all


def dew_point_c(temp_c: float, rh_pct: float) -> Optional[float]:
    """Magnus-Tetens dew point (derived). None when humidity is not above zero."""
    if rh_pct <= 0:
        return None
    g = math.log(rh_pct / 100.0) + MAGNUS_B * temp_c / (MAGNUS_C + temp_c)
    return MAGNUS_C * g / (MAGNUS_B - g)


def _in_range(v: str, x: float) -> bool:
    lo, hi = HARD_BOUNDS[v]
    return lo <= x <= hi


def _usable(v: str, x: Any) -> bool:
    """A real number inside the physical limits, not a sentinel: fit to serve as context."""
    return _finite(x) and x not in SENTINELS and _in_range(v, x)


def _obs(v: str, x: float) -> Dict[str, Any]:
    return {"value": x, "unit": UNIT[v], "basis": "measured"}


def _derived(value: float, unit: str, how: str) -> Dict[str, Any]:
    return {"value": round(value, 3), "unit": unit, "how": how, "basis": "derived"}


def _window(prior: Sequence[ClimateSample], ts: datetime, v: str, x: float, n: int = 8) -> List[Dict[str, Any]]:
    out = [{"time": s.timestamp.isoformat(), v: getattr(s, v), "basis": "measured"} for s in prior[-n:]]
    out.append({"time": ts.isoformat(), v: x, "basis": "measured"})
    return out


def _minutes(a: datetime, b: datetime) -> float:
    return (a - b).total_seconds() / 60.0


def _series(prior: Sequence[ClimateSample], v: str) -> List[Tuple[datetime, float]]:
    return [(s.timestamp, getattr(s, v)) for s in prior if _usable(v, getattr(s, v))]


def _context(ts: datetime, history: Sequence[ClimateSample]) -> Tuple[List[ClimateSample], Optional[str]]:
    """The contiguous tail of the history that may serve as context (consecutive gaps within MAX_GAP_MIN), or the reason there is none."""
    if not history:
        return [], "no earlier reading of this station"
    dt = _minutes(ts, history[-1].timestamp)
    if dt <= 0:
        return [], "this reading's timestamp is not after the previous reading's"
    if dt > MAX_GAP_MIN:
        return [], f"the previous reading is {dt:.0f} min old (context limit {MAX_GAP_MIN:g} min)"
    tail = [history[-1]]
    for s in reversed(history[:-1]):
        if _minutes(tail[0].timestamp, s.timestamp) > MAX_GAP_MIN:
            break
        tail.insert(0, s)
    return tail, None


# ------------------------------------------------------------------------------------------------ the checks
def run_weather_checks(sample: Mapping[str, Optional[float]], ts: datetime, history: Sequence[ClimateSample] = ()) -> WeatherResult:
    """Run every check whose needs the reading and the station's earlier readings satisfy. ``sample`` maps temperature, pressure and humidity to a
    value or None (not reported). ``history`` holds the station's EARLIER readings only (the caller keeps it causal)."""
    res = WeatherResult()
    hits, not_run = res.hits, res.not_run
    prior, ctx_reason = _context(ts, history)
    reported = {v: sample.get(v) for v in VARIABLES if sample.get(v) is not None}
    res.has_data = bool(reported)
    usable: Dict[str, float] = {}
    absent = [v for v in VARIABLES if v not in reported]

    # ---- integrity: sentinel, non-finite, out of limits
    for v, x in reported.items():
        if not _finite(x) or x in SENTINELS:
            hits.append(cat._hit("corrupt_value", "stream", f"{v} {x!r} is a corrupt value (non-finite or a sentinel)",
                                 {"variable": v, "observed": {"value": None if not _finite(x) else x, "text": repr(x), "unit": UNIT[v], "basis": "measured"},
                                  "threshold": _thr(list(SENTINELS), "values written by faulty loggers; also any non-finite number")}))
        elif not _in_range(v, x):
            lo, hi = HARD_BOUNDS[v]
            hits.append(cat._hit("value_out_of_range", "stream", f"{v} {x:g} {UNIT[v]} is outside the physical limits {lo:g} to {hi:g}",
                                 {"variable": v, "observed": _obs(v, x), "threshold": _thr([lo, hi], "physical limits (WMO-style); station pressure assumed for pressure")}))
        else:
            usable[v] = float(x)

    # ---- a variable that is missing now
    lookback = list(history[-DROPOUT_LOOKBACK:])
    for v in absent:
        if any(_usable(v, getattr(s, v)) for s in lookback):
            last = next(s for s in reversed(lookback) if _usable(v, getattr(s, v)))
            hits.append(cat._hit("dropout", "stream", f"{v} is missing although this station reported it in its last {DROPOUT_LOOKBACK} readings",
                                 {"variable": v, "threshold": _thr(DROPOUT_LOOKBACK, "readings looked back"),
                                  "window": [{"time": last.timestamp.isoformat(), v: getattr(last, v), "basis": "measured"}]}))
        elif reported:
            not_run.append({"check": v, "variable": v, "reason": f"{v} is not reported by this station (not in this reading nor in its last {len(lookback)} readings); none of its checks ran"})

    # ---- extreme temperature: magnitude alone, UNCERTAIN at most
    if "temperature" in usable and not EXTREME_TEMPERATURE[0] <= usable["temperature"] <= EXTREME_TEMPERATURE[1]:
        x = usable["temperature"]
        hits.append(cat._hit("extreme_value", "stream", f"temperature {x:g} C is extreme for most stations; nothing confirms it, so it is UNCERTAIN, not a fault",
                             {"variable": "temperature", "observed": _obs("temperature", x), "threshold": _thr(list(EXTREME_TEMPERATURE), "rare, so unconfirmed; magnitude alone is never a fault")}))

    # ---- reporting gap (needs the station's cadence)
    cad_src = list(history[-20:])
    diffs = [(b.timestamp - a.timestamp).total_seconds() for a, b in zip(cad_src, cad_src[1:]) if b.timestamp > a.timestamp]
    if len(history) < GAP_MIN_HISTORY or len(diffs) < GAP_MIN_HISTORY - 1:
        not_run.append({"check": "reporting_gap", "reason": f"{len(history)} earlier reading(s), {GAP_MIN_HISTORY} needed to know the cadence"})
    else:
        cadence = statistics.median(diffs)
        gap = (ts - history[-1].timestamp).total_seconds()
        if gap > max(GAP_FACTOR * cadence, GAP_ABS_MIN_S):
            hits.append(cat._hit("reporting_gap", "stream", f"{gap / 60:.1f} min since the previous reading; this station usually reports every {cadence / 60:.2f} min",
                                 {"variable": None, "observed": _derived(gap / 60, "min", "time since the previous reading"),
                                  "cadence": _derived(cadence / 60, "min", "median spacing of the last 20 readings"),
                                  "threshold": _thr(GAP_FACTOR, f"times the cadence, and at least {GAP_ABS_MIN_S:g} s")}))

    # ---- checks on the station's own earlier readings
    history_checks = ("frozen_value", "rate_of_change", "spike_vs_history", "level_shift")
    spike_dev: Dict[str, Tuple[float, float, float]] = {}      # variable -> (deviation, allowed, level)
    spike_hits: Dict[str, CheckHit] = {}
    for v, x in usable.items():
        if ctx_reason is not None:
            for name in history_checks:
                if not (name == "frozen_value" and v == "humidity" and x >= SATURATED_RH):
                    not_run.append({"check": name, "variable": v, "reason": ctx_reason})
            continue
        last = prior[-1]
        dt = _minutes(ts, last.timestamp)

        # frozen
        run: List[ClimateSample] = []                     # the identical readings just before this one, newest last
        for s in reversed(prior):
            if _finite(getattr(s, v)) and abs(getattr(s, v) - x) <= 1e-9:
                run.insert(0, s)
            else:
                break
        if v == "humidity" and x >= SATURATED_RH:
            not_run.append({"check": "frozen_value", "variable": v, "reason": "humidity at saturation can legitimately stay at 100 %"})
        elif len(prior) < FROZEN_N - 1:
            not_run.append({"check": "frozen_value", "variable": v, "reason": f"{len(prior)} earlier reading(s) in context, {FROZEN_N - 1} needed"})
        elif len(run) + 1 >= FROZEN_N:
            span = (ts - run[0].timestamp).total_seconds()
            if span < FROZEN_MIN_SPAN_S:
                not_run.append({"check": "frozen_value", "variable": v, "reason": f"{len(run) + 1} identical readings span only {span:.0f} s; {FROZEN_MIN_SPAN_S:g} s are needed before a repeat counts as a frozen sensor (a coarse sensor repeats a value at fast cadence)"})
            else:
                hits.append(cat._hit("frozen_value", "stream", f"{v} is {x:g} {UNIT[v]} in {len(run) + 1} readings in a row over {span:.0f} s",
                                     {"variable": v, "observed": _obs(v, x), "threshold": _thr([FROZEN_N, FROZEN_MIN_SPAN_S], "identical readings in a row, and seconds they must span"),
                                      "window": _window(run, ts, v, x, FROZEN_N)}))

        # rate of change (cadence-aware: a floor for noise plus an allowance per minute between the two readings)
        prev = getattr(last, v)
        if not _usable(v, prev):
            not_run.append({"check": "rate_of_change", "variable": v, "reason": f"the previous reading has no usable {v}"})
        else:
            limit = RATE_FLOOR[v] + RATE_PER_MIN[v] * dt
            step = abs(x - prev)
            if step > limit:
                hits.append(cat._hit("rate_of_change", "stream", f"{v} changed {step:.2f} {UNIT[v]} in {dt:.2f} min (limit {limit:.2f}); a fast change alone is unconfirmed, so UNCERTAIN",
                                     {"variable": v, "observed": _obs(v, x), "change": _derived(step, UNIT[v], "absolute difference to the previous reading"),
                                      "elapsed": _derived(dt, "min", "between the two readings"),
                                      "threshold": _thr(round(limit, 3), f"{RATE_FLOOR[v]:g} {UNIT[v]} plus {RATE_PER_MIN[v]:g} {UNIT[v]}/min"),
                                      "window": _window(prior, ts, v, x, 2)}))

        series = _series(prior, v)
        # spike against a robust level of the station's own history
        vals = [val for _, val in series][-SPIKE_WINDOW:]
        if len(vals) < SPIKE_MIN:
            not_run.append({"check": "spike_vs_history", "variable": v, "reason": f"{len(vals)} usable earlier {v} readings in context, {SPIKE_MIN} needed"})
        else:
            level = statistics.median(vals[-LEVEL_N:])
            d = [b - a for a, b in zip(vals, vals[1:])]
            md = statistics.median(d)
            scale = max(1.4826 * statistics.median([abs(e - md) for e in d]), SPIKE_SCALE_FLOOR[v])
            minutes = _minutes(ts, series[-min(len(series), LEVEL_N // 2 + 1)][0])
            allowed = max(SPIKE_K * scale, SPIKE_ABS[v] + NATURAL_PER_MIN[v] * minutes)
            dev = abs(x - level)
            spike_dev[v] = (dev, allowed, level)
            # A return to the level BEFORE an episode is not a new anomaly: the recent median is still contaminated by the episode, so compare with
            # the readings older than the last SPIKE_RECENT_SKIP (bounded, causal). A permanent shift stays away from that level and is still hit.
            older = [val for _, val in series[:-SPIKE_RECENT_SKIP]][-SPIKE_WINDOW:]
            returned = len(older) >= SPIKE_MIN and abs(x - statistics.median(older)) <= allowed
            if dev > allowed and not returned:
                spike_hits[v] = cat._hit("spike_vs_history", "stream", f"{v} {x:g} {UNIT[v]} is {dev:.2f} away from its recent level {level:.2f} (limit {allowed:.2f})",
                                         {"variable": v, "observed": _obs(v, x), "level": _derived(level, UNIT[v], f"median of the last {LEVEL_N} usable readings"),
                                          "deviation": _derived(dev, UNIT[v], "absolute difference to the level"),
                                          "threshold": _thr(round(allowed, 3), f"larger of {SPIKE_K:g} robust sigmas ({scale:.3f}) and {SPIKE_ABS[v]:g} {UNIT[v]} plus {NATURAL_PER_MIN[v]:g} {UNIT[v]}/min"),
                                          "window": _window(prior, ts, v, x, 10)})

        # sustained level shift (drift)
        if len(series) < SHIFT_N:
            not_run.append({"check": "level_shift", "variable": v, "reason": f"{len(series)} usable earlier {v} readings in context, {SHIFT_N} needed"})
        else:
            base = series[-SHIFT_N:-SHIFT_RECENT_EXCLUDE]
            bvals = [val for _, val in base]
            baseline = statistics.median(bvals)
            recent_vals = [val for _, val in series[-2:]] + [x]
            recent = sum(recent_vals) / len(recent_vals)
            centre = sum(t.timestamp() for t, _ in base) / len(base)
            minutes = (ts.timestamp() - centre) / 60.0
            allowed = SHIFT_ABS[v] + SHIFT_NATURAL_PER_MIN[v] * minutes
            shift = recent - baseline
            if abs(shift) > allowed:
                hits.append(cat._hit("level_shift", "stream", f"the last readings of {v} sit {abs(shift):.2f} {UNIT[v]} {'above' if shift > 0 else 'below'} its earlier level (limit {allowed:.2f}); a sustained shift can be real weather, so UNCERTAIN",
                                     {"variable": v, "observed": _obs(v, x), "baseline": _derived(baseline, UNIT[v], f"median of {len(base)} earlier readings"),
                                      "shift": _derived(shift, UNIT[v], "mean of the last 3 readings minus the baseline"),
                                      "threshold": _thr(round(allowed, 3), f"{SHIFT_ABS[v]:g} {UNIT[v]} plus {SHIFT_NATURAL_PER_MIN[v]:g} {UNIT[v]}/min over the elapsed time"),
                                      "window": _window(prior, ts, v, x, 10)}))

    # ---- dew point consistency (temperature and humidity)
    now_dp: Optional[float] = None
    if "temperature" in usable and "humidity" in usable:
        t, rh = usable["temperature"], usable["humidity"]
        now_dp = dew_point_c(t, rh)
        if now_dp is not None and now_dp > t + DEWPOINT_ABOVE_TEMPERATURE_C:
            hits.append(cat._hit("dewpoint_above_temperature", "stream", f"the dew point {now_dp:.1f} C derived from temperature and humidity is above the temperature {t:g} C, which cannot happen",
                                 {"variable": "humidity", "observed": _obs("humidity", rh), "dew_point": _derived(now_dp, "C", "Magnus-Tetens from temperature and humidity"),
                                  "temperature": _obs("temperature", t), "threshold": _thr(DEWPOINT_ABOVE_TEMPERATURE_C, "C of tolerance")}))
        if now_dp is not None and ctx_reason is None:
            last = prior[-1]
            if _usable("temperature", last.temperature) and _usable("humidity", last.humidity):
                prev_dp = dew_point_c(last.temperature, last.humidity)  # type: ignore[arg-type]
                dt = _minutes(ts, last.timestamp)
                limit = DEWPOINT_STEP_C + DEWPOINT_PER_MIN * dt
                if prev_dp is not None and abs(now_dp - prev_dp) > limit:
                    hits.append(cat._hit("dewpoint_jump", "stream", f"the dew point derived from temperature and humidity moved {now_dp - prev_dp:+.1f} C in {dt:.2f} min (limit {limit:.1f}); the dew point normally changes slowly",
                                         {"variable": "humidity", "observed": _obs("humidity", rh), "dew_point": _derived(now_dp, "C", "Magnus-Tetens from temperature and humidity"),
                                          "previous_dew_point": _derived(prev_dp, "C", "Magnus-Tetens from the previous reading"),
                                          "threshold": _thr(round(limit, 3), f"{DEWPOINT_STEP_C:g} C plus {DEWPOINT_PER_MIN:g} C/min")}))
            else:
                not_run.append({"check": "dewpoint_jump", "variable": "temperature,humidity", "reason": "the previous reading has no usable temperature and humidity"})
    elif reported:
        missing = [v for v in ("temperature", "humidity") if v not in usable]
        reason = f"needs temperature and humidity in the reading; no usable {' and '.join(missing)}"
        for name in ("dewpoint_above_temperature", "dewpoint_jump"):
            not_run.append({"check": name, "variable": "temperature,humidity", "reason": reason})

    # ---- genuine extreme or fault: do the variables deviate TOGETHER with a steady dew point?
    if spike_hits:
        moving = [v for v, (dev, allowed, _) in spike_dev.items() if dev > CORROBORATION_FRACTION * allowed]
        dp_level = None
        if "temperature" in spike_dev and "humidity" in spike_dev:
            dp_level = dew_point_c(spike_dev["temperature"][2], spike_dev["humidity"][2])
        coherent = len(moving) >= 2 and now_dp is not None and dp_level is not None and abs(now_dp - dp_level) <= DEWPOINT_COHERENT_C
        for v, h in spike_hits.items():
            corr: Dict[str, Any] = {"coherent": coherent, "variables_moving": moving, "threshold": _thr(DEWPOINT_COHERENT_C, "C of dew point change that still counts as steady")}
            if now_dp is not None and dp_level is not None:
                corr["dew_point_now"] = _derived(now_dp, "C", "Magnus-Tetens from temperature and humidity")
                corr["dew_point_level"] = _derived(dp_level, "C", "Magnus-Tetens from the recent levels of temperature and humidity")
            else:
                corr["note"] = "the dew point could not be derived, so nothing corroborates the deviation"
            h.evidence["corroboration"] = corr
            if coherent:
                h.kind, h.weight = "uncertain", 0.30
                h.reason += "; other variables moved with it and the dew point stayed steady, so this is a genuine-extreme candidate, not a fault"
            elif len(moving) >= 2:
                h.reason += "; other variables moved with it, but the dew point did not stay steady (or could not be derived), so nothing confirms a genuine extreme"
            else:
                h.reason += " and nothing else moves with it"
            hits.append(h)
    return res
