"""The one check catalogue for rainfall validation (spec section 4).

It merges the checks of the former live one-gauge scorer (backend/app/rainfall/scorer.py, deleted; see git history) and the daily one-station scorer
(ml-service/qc/station.py). Each check declares what it needs; a run executes the checks its input satisfies and lists the rest
as "not run: reason". Nothing is skipped silently.

METHOD: fixed rules, one statistic (a gamma upper tail on the gauge's own earlier wet days) and a neighbour check. It is NOT a
trained model. Every weight and threshold below is a design choice, uncalibrated; there are no labels to calibrate against.

Verdicts per row: NO_DATA (nothing usable in the row), SUSPECT (a fault-kind check fired: impossible value or internal
inconsistency), UNCERTAIN (only an uncertain-kind check fired: an isolated wet or dry reading, a heavy value nobody confirms, a
duplicate row), OK. Magnitude alone never makes a row SUSPECT except above the physical ceiling; a heavy daily value is UNCERTAIN
unless neighbours also report rain, in which case it is recorded as corroborated and does not change the verdict.

The rule score is 1 - prod(1 - weight) over the fired checks: an ordering of suspicion in [0, 1], never a probability. Severity is
three bands of it (high >= 0.7, medium >= 0.3, low below 0.3), a design choice.
"""
from __future__ import annotations

import math
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from backend.app.geo import haversine_distance_km
from backend.app.validation.records import DailyTotal, Reading

METHOD = "rules + own-history statistic + neighbour check (not a trained model); weights and thresholds are design choices, not calibrated"

# ---- thresholds (design choices, uncalibrated)
INTENSITY_CEILING = 300.0     # mm/h; assumed unit on live data
JUMP_MM = 50.0                # counter increase between consecutive readings, cumulative mode
FROZEN_N = 6                  # identical non-zero intensities in a row
MISMATCH_N = 3                # readings with intensity > 0 but a flat counter
DAILY_MAX_MM = 1000.0         # above any recorded Indian 24-hour total
REPEAT_DAYS = 3               # the same positive daily value on this many consecutive days
WET_DAY_MM = 0.1
CLIM_WINDOW_DAYS = 15
CLIM_MIN_WET = 30
CLIM_TAIL_P = 1e-3            # upper-tail probability below which the day is a heavy value
NEIGHBOUR_RADIUS_KM = 10.0
MIN_NEIGHBOURS = 3
NEIGHBOUR_AGREE = 0.75
HIGH, MEDIUM = 0.7, 0.3


@dataclass(frozen=True)
class CheckSpec:
    name: str
    profile: str          # "reading" | "daily"
    layer: str            # "rule" | "statistic" | "neighbour" | "integrity"
    kind: str             # "fault" (-> SUSPECT) | "uncertain" (-> UNCERTAIN) | "info" (no verdict change)
    weight: float
    needs: str            # what the input must provide


CATALOGUE: Dict[str, CheckSpec] = {c.name: c for c in [
    CheckSpec("negative_value", "reading", "rule", "fault", 0.95, "a value"),
    CheckSpec("intensity_above_ceiling", "reading", "rule", "fault", 0.90, "an intensity value"),
    CheckSpec("counter_jump", "reading", "rule", "fault", 0.70, "cumulative accumulation and a previous reading"),
    CheckSpec("counter_reset", "reading", "rule", "info", 0.10, "cumulative accumulation and a previous reading"),
    CheckSpec("frozen_intensity", "reading", "rule", "fault", 0.60, f"{FROZEN_N} consecutive intensity values"),
    CheckSpec("intensity_counter_mismatch", "reading", "rule", "fault", 0.50, "cumulative accumulation and intensity, "
                                                                              f"{MISMATCH_N + 1} consecutive readings"),
    CheckSpec("neighbour_isolated_wet", "reading", "neighbour", "uncertain", 0.30, f"{MIN_NEIGHBOURS}+ stations with coordinates within {NEIGHBOUR_RADIUS_KM:g} km"),
    CheckSpec("neighbour_isolated_dry", "reading", "neighbour", "uncertain", 0.30, f"{MIN_NEIGHBOURS}+ stations with coordinates within {NEIGHBOUR_RADIUS_KM:g} km"),
    CheckSpec("impossible_value", "daily", "rule", "fault", 0.95, "a daily total"),
    CheckSpec("repeated_value", "daily", "rule", "fault", 0.60, f"{REPEAT_DAYS} consecutive complete days"),
    CheckSpec("climatology_upper_tail", "daily", "statistic", "uncertain", 0.30, f"{CLIM_MIN_WET} earlier wet days near the day of year"),
    CheckSpec("neighbour_isolated_wet", "daily", "neighbour", "uncertain", 0.30, f"{MIN_NEIGHBOURS}+ stations with coordinates within {NEIGHBOUR_RADIUS_KM:g} km"),
    CheckSpec("neighbour_isolated_dry", "daily", "neighbour", "uncertain", 0.30, f"{MIN_NEIGHBOURS}+ stations with coordinates within {NEIGHBOUR_RADIUS_KM:g} km"),
    CheckSpec("duplicate_row", "both", "integrity", "uncertain", 0.30, "repeated station and time"),
]}
# the catalogue is keyed by name; a name shared by two profiles (the neighbour checks) is stored once, the profile only labels the family
INTEGRITY_NO_DATA = ("missing_value", "non_numeric", "bad_timestamp", "bad_day")


@dataclass
class CheckHit:
    check: str
    layer: str
    kind: str
    weight: float
    reason: str                       # one plain sentence
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RowResult:
    row_ref: Union[int, str]
    station_id: str
    verdict: str
    rule_score: float
    severity: Optional[str]
    hits: List[CheckHit] = field(default_factory=list)


@dataclass
class CatalogueResult:
    profile: str
    results: List[RowResult]                      # same order as the input records
    not_run: List[Dict[str, str]]                 # {"check", "reason", optional "station_id"}
    method: str = METHOD


# ------------------------------------------------------------------------------------------------ helpers

def rule_score(hits: Sequence[CheckHit]) -> float:
    p = 1.0
    for h in hits:
        p *= 1.0 - h.weight
    return round(1.0 - p, 3)


def severity(score: float) -> Optional[str]:
    if score <= 0:
        return None
    return "high" if score >= HIGH else "medium" if score >= MEDIUM else "low"


def _num_ev(value: float, unit: str, confirmed: bool) -> Dict[str, Any]:
    return {"value": value, "unit": unit, "basis": "measured" if confirmed else "assumed"}


def _thr(value: Any, why: str = "design choice, uncalibrated") -> Dict[str, Any]:
    return {"value": value, "why": why, "basis": "assumed"}


def _hit(check: str, profile: str, reason: str, evidence: Dict[str, Any]) -> CheckHit:
    spec = CATALOGUE[check]
    evidence = {"check": check, "layer": spec.layer, "profile": profile, **evidence}
    return CheckHit(check, spec.layer, spec.kind, spec.weight, reason, evidence)


def _verdict(hits: Sequence[CheckHit], no_data: bool) -> str:
    if no_data:
        return "NO_DATA"
    if any(h.kind == "fault" for h in hits):
        return "SUSPECT"
    if any(h.kind == "uncertain" for h in hits):
        return "UNCERTAIN"
    return "OK"


def _integrity_hits(rec: Union[Reading, DailyTotal], profile: str) -> Tuple[List[CheckHit], bool]:
    """Input-integrity issues from the parser as hits; -> (hits, row has no usable data)."""
    hits: List[CheckHit] = []
    no_data = False
    for i in rec.issues:
        if i.code in INTEGRITY_NO_DATA:
            no_data = True
        elif i.code in ("duplicate_timestamp", "duplicate_day"):
            hits.append(_hit("duplicate_row", profile, i.message, {"issue": i.code, "row_ref": rec.row_ref}))
    return hits, no_data


def _neighbour_map(stations: Dict[str, Tuple[Optional[float], Optional[float]]], radius_km: float) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    ids = [s for s, (la, lo) in stations.items() if la is not None and lo is not None]
    for s in ids:
        la, lo = stations[s]
        out[s] = [t for t in ids if t != s and haversine_distance_km(la, lo, stations[t][0], stations[t][1]) <= radius_km]  # type: ignore[arg-type]
    return out


def _coords(recs: Sequence[Union[Reading, DailyTotal]]) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    out: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
    for r in recs:
        if r.station_id not in out or out[r.station_id][0] is None:
            out[r.station_id] = (r.latitude, r.longitude)
    return out


def _neighbour_vote(cur_wet: bool, votes: List[Tuple[str, bool]], dist: Dict[str, float], profile: str, unit_note: str) -> Optional[CheckHit]:
    used = len(votes)
    if used < MIN_NEIGHBOURS:
        return None
    n_dry = sum(1 for _, w in votes if not w)
    n_wet = used - n_dry
    ev = {"neighbours": [{"station_id": s, "distance_km": round(dist[s], 2), "wet": w, "basis": "measured"} for s, w in votes],
          "threshold": _thr(NEIGHBOUR_AGREE, f"share of neighbours that must disagree; radius {NEIGHBOUR_RADIUS_KM:g} km, {MIN_NEIGHBOURS}+ neighbours")}
    if cur_wet and n_dry / used >= NEIGHBOUR_AGREE:
        return _hit("neighbour_isolated_wet", profile, f"wet here while {n_dry} of {used} neighbours within {NEIGHBOUR_RADIUS_KM:g} km are dry{unit_note}", ev)
    if not cur_wet and n_wet / used >= NEIGHBOUR_AGREE:
        return _hit("neighbour_isolated_dry", profile, f"dry here while {n_wet} of {used} neighbours within {NEIGHBOUR_RADIUS_KM:g} km are wet{unit_note}", ev)
    return None


# ------------------------------------------------------------------------------------------------ reading profile

def run_reading_checks(readings: Sequence[Reading], interval_minutes: Optional[float] = None,
                       radius_km: float = NEIGHBOUR_RADIUS_KM, align_minutes: Optional[float] = None) -> CatalogueResult:
    align = align_minutes if align_minutes is not None else (interval_minutes / 2.0 if interval_minutes else 10.0)
    by_station: Dict[str, List[Reading]] = defaultdict(list)
    for r in readings:
        if r.timestamp is not None:
            by_station[r.station_id].append(r)
    for lst in by_station.values():
        lst.sort(key=lambda r: r.timestamp)  # type: ignore[arg-type, return-value]

    # own previous reading with an accumulation value, and wet flag, per reading
    prev_acc: Dict[int, Optional[Reading]] = {}
    wet: Dict[int, bool] = {}
    for lst in by_station.values():
        last: Optional[Reading] = None
        for r in lst:
            prev_acc[id(r)] = last
            if r.accumulation_mode == "per_reading":      # the value IS the rain of this interval
                inc = r.accumulation is not None and r.accumulation > 0
            else:                                         # cumulative counter: rain means it rose since the previous reading
                inc = last is not None and r.accumulation is not None and last.accumulation is not None and r.accumulation > last.accumulation
            wet[id(r)] = bool((r.intensity is not None and r.intensity > 0) or inc)
            if r.accumulation is not None:
                last = r

    epoch: Dict[str, List[float]] = {sid: [x.timestamp.timestamp() for x in lst] for sid, lst in by_station.items()}  # type: ignore[union-attr]
    coords = _coords(readings)
    nmap = _neighbour_map(coords, radius_km)
    not_run: List[Dict[str, str]] = []
    nb_ok: Dict[str, bool] = {}
    for sid in by_station:
        la, lo = coords.get(sid, (None, None))
        if la is None or lo is None:
            nb_ok[sid] = False
            not_run.append({"check": "neighbour", "station_id": sid, "reason": "no coordinates for this station"})
        elif len(nmap.get(sid, [])) < MIN_NEIGHBOURS:
            nb_ok[sid] = False
            not_run.append({"check": "neighbour", "station_id": sid,
                            "reason": f"{len(nmap.get(sid, []))} station(s) with coordinates within {radius_km:g} km, {MIN_NEIGHBOURS} needed"})
        else:
            nb_ok[sid] = True

    mixed_time = any(r.time_basis == "received" for r in readings)
    unit_note = " (received-time stamps make this comparison weaker)" if mixed_time else ""
    results: Dict[int, RowResult] = {}
    for sid, lst in by_station.items():
        for idx, r in enumerate(lst):
            hits, no_data = _integrity_hits(r, "reading")
            has_value = r.accumulation is not None or r.intensity is not None
            if not has_value:
                no_data = True
            ev_base = {"row_ref": r.row_ref, "time_basis": r.time_basis}
            c = r.units_confirmed
            if has_value and not no_data:
                if (r.intensity is not None and r.intensity < 0) or (r.accumulation is not None and r.accumulation < 0):
                    v = r.intensity if (r.intensity is not None and r.intensity < 0) else r.accumulation
                    hits.append(_hit("negative_value", "reading", f"a negative rainfall value ({v:g}) is impossible",
                                     {**ev_base, "observed": _num_ev(v, "mm", c), "threshold": _thr(0, "physical: rainfall cannot be negative")}))
                if r.intensity is not None and r.intensity > INTENSITY_CEILING:
                    hits.append(_hit("intensity_above_ceiling", "reading", f"intensity {r.intensity:g} mm/h is above the physical ceiling of {INTENSITY_CEILING:g}",
                                     {**ev_base, "observed": _num_ev(r.intensity, "mm/h", c), "threshold": _thr(INTENSITY_CEILING, "above any plausible one-minute rate")}))
                cumulative = r.accumulation_mode == "cumulative"
                p = prev_acc.get(id(r))
                if cumulative and r.accumulation is not None and p is not None and p.accumulation is not None:
                    step = r.accumulation - p.accumulation
                    win = [{"row_ref": p.row_ref, "accumulation": p.accumulation, "basis": "measured"}, {"row_ref": r.row_ref, "accumulation": r.accumulation, "basis": "measured"}]
                    if step > JUMP_MM:
                        hits.append(_hit("counter_jump", "reading", f"the counter rose {step:.1f} between consecutive readings (limit {JUMP_MM:g})",
                                         {**ev_base, "observed": _num_ev(step, "mm", c), "threshold": _thr(JUMP_MM), "window": win}))
                    elif step < 0:
                        hits.append(_hit("counter_reset", "reading", f"the counter fell from {p.accumulation:g} to {r.accumulation:g} (a reset)",
                                         {**ev_base, "observed": _num_ev(step, "mm", c), "window": win}))
                recent = [x for x in lst[max(0, idx - FROZEN_N + 1): idx + 1] if x.intensity is not None]
                if len(recent) == FROZEN_N and len(lst[max(0, idx - FROZEN_N + 1): idx + 1]) == FROZEN_N and r.intensity and r.intensity > 0 \
                        and len({x.intensity for x in recent}) == 1:
                    hits.append(_hit("frozen_intensity", "reading", f"intensity {r.intensity:g} is unchanged for {FROZEN_N} readings",
                                     {**ev_base, "observed": _num_ev(r.intensity, "mm/h", c), "threshold": _thr(FROZEN_N),
                                      "window": [{"row_ref": x.row_ref, "intensity": x.intensity, "basis": "measured"} for x in recent]}))
                if cumulative:
                    tail = [x for x in lst[max(0, idx - MISMATCH_N): idx + 1]]
                    if len(tail) == MISMATCH_N + 1 and all(x.accumulation is not None and x.intensity is not None for x in tail) \
                            and all(x.intensity > 0 for x in tail[1:]) and len({x.accumulation for x in tail}) == 1:
                        hits.append(_hit("intensity_counter_mismatch", "reading", f"intensity is above zero for {MISMATCH_N} readings but the counter did not move",
                                         {**ev_base, "observed": _num_ev(r.intensity, "mm/h", c), "threshold": _thr(MISMATCH_N),
                                          "window": [{"row_ref": x.row_ref, "intensity": x.intensity, "accumulation": x.accumulation, "basis": "measured"} for x in tail]}))
                if nb_ok.get(sid):
                    la, lo = coords[sid]
                    votes: List[Tuple[str, bool]] = []
                    dist: Dict[str, float] = {}
                    for nid in nmap[sid]:
                        near = _nearest(by_station.get(nid, []), epoch[nid], r, align)
                        if near is not None:
                            votes.append((nid, wet[id(near)]))
                            dist[nid] = haversine_distance_km(la, lo, coords[nid][0], coords[nid][1])  # type: ignore[arg-type]
                    h = _neighbour_vote(wet[id(r)], votes, dist, "reading", unit_note)
                    if h:
                        h.evidence.update(ev_base)
                        hits.append(h)
            score = rule_score(hits)
            results[id(r)] = RowResult(r.row_ref, sid, _verdict(hits, no_data), 0.0 if no_data else score, None if no_data else severity(score), hits)

    out: List[RowResult] = []
    for r in readings:
        res = results.get(id(r))
        if res is None:                                   # no usable timestamp: kept, NO_DATA, with its reasons
            hits, _ = _integrity_hits(r, "reading")
            res = RowResult(r.row_ref, r.station_id, "NO_DATA", 0.0, None, hits)
        out.append(res)
    if not by_station:
        not_run.append({"check": "all", "reason": "no reading has a usable timestamp"})
    return CatalogueResult("reading", out, not_run)


def _nearest(series: Sequence[Reading], times: Sequence[float], ref: Reading, align_minutes: float) -> Optional[Reading]:
    """The reading of `series` (sorted; `times` are its epoch seconds) closest in time to `ref`, within align_minutes. O(log n)."""
    t = ref.timestamp.timestamp()  # type: ignore[union-attr]
    i = bisect_left(times, t)
    best, best_d = None, None
    for j in (i - 1, i):
        if 0 <= j < len(times):
            d = abs(times[j] - t) / 60.0
            if d <= align_minutes and (best_d is None or d < best_d):
                best, best_d = series[j], d
    return best


# ------------------------------------------------------------------------------------------------ daily profile

def _gamma_tail(history: List[Tuple[int, float]], doy: int, mm: float) -> Tuple[Optional[float], int]:
    """Upper-tail probability of mm under a gamma (method of moments) fitted to earlier wet days near the day of year."""
    from scipy.stats import gamma
    near = [v for d, v in history if min(abs(d - doy), 366 - abs(d - doy)) <= CLIM_WINDOW_DAYS]
    n = len(near)
    if n < CLIM_MIN_WET or mm < WET_DAY_MM:
        return None, n
    x = np.asarray(near, dtype=float)
    mean, var = float(x.mean()), float(x.var())
    if var <= 0 or mean <= 0:
        return None, n
    return float(gamma.sf(mm, a=mean * mean / var, scale=var / mean)), n


def run_daily_checks(totals: Sequence[DailyTotal], radius_km: float = NEIGHBOUR_RADIUS_KM) -> CatalogueResult:
    by_station: Dict[str, List[DailyTotal]] = defaultdict(list)
    for t in totals:
        if t.day is not None:
            by_station[t.station_id].append(t)
    for lst in by_station.values():
        lst.sort(key=lambda t: t.day)  # type: ignore[arg-type, return-value]

    coords = _coords(totals)
    nmap = _neighbour_map(coords, radius_km)
    by_day: Dict[Tuple[str, date], DailyTotal] = {(t.station_id, t.day): t for lst in by_station.values() for t in lst if t.day is not None and t.mm is not None}  # type: ignore[misc]
    not_run: List[Dict[str, str]] = []
    nb_ok: Dict[str, bool] = {}
    for sid in by_station:
        la, lo = coords.get(sid, (None, None))
        if la is None or lo is None:
            nb_ok[sid] = False
            not_run.append({"check": "neighbour", "station_id": sid, "reason": "no coordinates for this station"})
        elif len(nmap.get(sid, [])) < MIN_NEIGHBOURS:
            nb_ok[sid] = False
            not_run.append({"check": "neighbour", "station_id": sid,
                            "reason": f"{len(nmap.get(sid, []))} station(s) with coordinates within {radius_km:g} km, {MIN_NEIGHBOURS} needed"})
        else:
            nb_ok[sid] = True

    results: Dict[int, RowResult] = {}
    for sid, lst in by_station.items():
        history: List[Tuple[int, float]] = []
        run, last = 1, None
        clim_max_n, clim_ran = 0, False
        for t in lst:
            hits, no_data = _integrity_hits(t, "daily")
            if t.mm is None:
                no_data = True
            ev_base = {"row_ref": t.row_ref, "day": t.day.isoformat(), "time_basis": "observed"}
            if not no_data:
                mm = t.mm  # type: ignore[assignment]
                c = t.units_confirmed
                impossible = mm < 0 or mm > DAILY_MAX_MM
                if impossible:
                    hits.append(_hit("impossible_value", "daily", f"a daily total of {mm:g} mm is impossible (limit 0 to {DAILY_MAX_MM:g})",
                                     {**ev_base, "observed": _num_ev(mm, "mm", c), "threshold": _thr(DAILY_MAX_MM, "above any recorded Indian 24-hour total; below zero is impossible")}))
                # repeated positive value on consecutive days; days known to be incomplete are skipped
                if last is not None and mm > 0 and mm == last[1] and (t.day - last[0]).days == 1 and t.complete is not False and last[2] is not False:
                    run += 1
                else:
                    run = 1
                if run >= REPEAT_DAYS:
                    hits.append(_hit("repeated_value", "daily", f"the same positive value {mm:g} mm on {run} consecutive days",
                                     {**ev_base, "observed": _num_ev(mm, "mm", c), "threshold": _thr(REPEAT_DAYS),
                                      "window": [{"day": (t.day).isoformat(), "mm": mm, "basis": "measured"}]}))
                tail_p, n_hist = _gamma_tail(history, t.day.timetuple().tm_yday, mm)
                clim_max_n = max(clim_max_n, n_hist)
                clim_tail_hit: Optional[CheckHit] = None
                if tail_p is not None:
                    clim_ran = True
                    if tail_p < CLIM_TAIL_P:
                        clim_tail_hit = _hit("climatology_upper_tail", "daily",
                                             f"{mm:g} mm is a heavy value for this gauge (upper-tail probability {tail_p:.2g} on its own {n_hist} earlier wet days)",
                                             {**ev_base, "observed": _num_ev(mm, "mm", c), "threshold": _thr(CLIM_TAIL_P, "upper-tail probability"),
                                              "history": {"n_wet_days": n_hist, "basis": "derived"}, "tail_probability": {"value": tail_p, "basis": "derived"}})
                nb_hit: Optional[CheckHit] = None
                corroborated = False
                if nb_ok.get(sid):
                    la, lo = coords[sid]
                    votes, dist = [], {}
                    for nid in nmap[sid]:
                        o = by_day.get((nid, t.day))
                        if o is not None and o.mm is not None:
                            votes.append((nid, o.mm >= WET_DAY_MM))
                            dist[nid] = haversine_distance_km(la, lo, coords[nid][0], coords[nid][1])  # type: ignore[arg-type]
                    cur_wet = mm >= WET_DAY_MM
                    nb_hit = _neighbour_vote(cur_wet, votes, dist, "daily", "")
                    if nb_hit:
                        nb_hit.evidence.update(ev_base)
                    corroborated = len(votes) >= MIN_NEIGHBOURS and cur_wet and sum(1 for _, w in votes if w) / len(votes) >= NEIGHBOUR_AGREE
                if clim_tail_hit is not None:
                    if corroborated:      # neighbours also report rain: a genuine extreme is never called a fault
                        clim_tail_hit.kind, clim_tail_hit.weight = "info", 0.0
                        clim_tail_hit.reason += "; neighbours also report rain, so it is corroborated"
                    hits.append(clim_tail_hit)
                if nb_hit is not None:
                    hits.append(nb_hit)
                last = (t.day, mm, t.complete)
                if not impossible and mm >= WET_DAY_MM:
                    history.append((t.day.timetuple().tm_yday, mm))
            score = rule_score(hits)
            results[id(t)] = RowResult(t.row_ref, sid, _verdict(hits, no_data), 0.0 if no_data else score, None if no_data else severity(score), hits)
        if not clim_ran:
            not_run.append({"check": "climatology_upper_tail", "station_id": sid,
                            "reason": f"never reached {CLIM_MIN_WET} earlier wet days near the day of year (most: {clim_max_n})"})

    out: List[RowResult] = []
    for t in totals:
        res = results.get(id(t))
        if res is None:
            hits, _ = _integrity_hits(t, "daily")
            res = RowResult(t.row_ref, t.station_id, "NO_DATA", 0.0, None, hits)
        out.append(res)
    if not by_station:
        not_run.append({"check": "all", "reason": "no row has a usable day"})
    return CatalogueResult("daily", out, not_run)


def run_checks(records: Sequence[Union[Reading, DailyTotal]], profile: str, interval_minutes: Optional[float] = None) -> CatalogueResult:
    if profile == "reading":
        return run_reading_checks(records, interval_minutes)  # type: ignore[arg-type]
    if profile == "daily":
        return run_daily_checks(records)  # type: ignore[arg-type]
    raise ValueError("profile must be 'reading' or 'daily'")
