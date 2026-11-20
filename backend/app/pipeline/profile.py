"""The variable profile of a dataset: what the stored values ARE, detected from the data, then edited by the user where they know better.

Cleaning that is right for one variable is wrong for another (a missing hour of temperature can be filled; a missing hour of a file that
lists only non-zero rainfall hours may be a dry hour). So cleaning and exploring read the profile, never a hard-coded parameter.

Detected from the data (never guessed silently; every number in ``evidence`` is a real count):
* ``reports_zero_values``: zeros are present. This is DATA-DETECTED and wins over an importer's own flag (``omits_zero_values``, or the older
  ``omits_zero_hours``, read by name); a disagreement is written into the evidence.
* ``cadence``: the median interval between consecutive reported values and whether most intervals equal it.
* ``kind``: ``intermittent_accumulation`` (rainfall-like: many zeros or jumpy), ``continuous_state`` (temperature-like: smooth between steps)
  or ``unknown``. A parameter the importer or the user names with a registered default (``PARAMETER_DEFAULTS``) takes that kind.

Editable by the user (``save_overrides``): parameter, kind, units, valid_range, missing_codes. ``reports_zero_values`` is not editable: it is a
property of the data. NOT claimed: that a detected kind is right; it is a rule-based judgement and the evidence says what it rested on.
"""
from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.pipeline.models import Observation, PipelineProfile
from backend.app.validation import checks

KINDS = ("intermittent_accumulation", "continuous_state", "unknown")
RAINFALL = "rainfall"
# Registered parameters. Adding a parameter here (or editing a profile) is all the explore and cleaning layers need; they read nothing else.
PARAMETER_DEFAULTS: Dict[str, Dict[str, Any]] = {
    RAINFALL: {"kind": "intermittent_accumulation", "units": "mm", "valid_range": [0.0, checks.INTENSITY_CEILING],
               "range_note": "0 to the platform's hourly ceiling (an assumed design limit, not a measured one)"},
    # Other parameters are DATA, not code paths: the cleaning and explore layers read only these fields. The bounds are ASSUMED plausible limits, to be edited
    # for the station; a value outside them is only proposed for exclusion, never silently dropped. Wind speed has real zeros (calm), so it is a continuous
    # state with a lower bound of 0: its zeros are values, short gaps may be filled, and a linear fill between non-negative values cannot go below 0.
    "temperature": {"kind": "continuous_state", "units": "degC", "valid_range": [-90.0, 60.0], "range_note": "assumed plausible air temperature bounds"},
    "relative_humidity": {"kind": "continuous_state", "units": "%", "valid_range": [0.0, 100.0], "range_note": "relative humidity is bounded 0 to 100 by definition"},
    "pressure": {"kind": "continuous_state", "units": "hPa", "valid_range": [300.0, 1100.0], "range_note": "assumed plausible pressure bounds (a high station can read lower)"},
    "wind_speed": {"kind": "continuous_state", "units": "m/s", "valid_range": [0.0, 120.0], "range_note": "0 (calm) to an assumed upper bound; speed cannot be negative"},
}
GENERATED_ONLY_NOTE = ("profile detection and the cleaning defaults are tested on GENERATED data only (no real sample file of any parameter has been profiled); "
                       "treat a detected kind as a suggestion and edit the profile where you know better")
CANDIDATE_MISSING_CODES = (-9999.0, -999.0, -99.0, 99.0, 999.0, 9999.0)
SAMPLE_STATIONS, SAMPLE_PER_STATION = 30, 5000
ZERO_SHARE_INTERMITTENT = 0.2
SMOOTH_RATIO = 0.5
MIN_PAIRS = 20
MIN_VALUES = 30
REGULAR_SHARE = 0.8
EDITABLE = ("parameter", "kind", "units", "valid_range", "missing_codes")


def source_module(source: str):
    """The importer module of a source, found by name (never edited here), or None."""
    try:
        from backend.app.pipeline import jobs
        mod = jobs.SOURCES.get(source)
        if mod is not None:
            return mod
    except Exception:
        pass
    try:
        from backend.app.pipeline import importers
        reg = getattr(importers, "SOURCES", None)
        if isinstance(reg, dict) and source in reg:
            return reg[source]
    except Exception:
        pass
    return None


def module_flag(source: str) -> Optional[bool]:
    """The importer's own declaration that it omits zero values: ``omits_zero_values``, else ``omits_zero_hours``, else None (not declared)."""
    mod = source_module(source)
    if mod is None:
        return None
    for name in ("omits_zero_values", "omits_zero_hours"):
        if hasattr(mod, name):
            return bool(getattr(mod, name))
    return None


def _utc(t: datetime) -> datetime:
    return t if t.tzinfo is not None else t.replace(tzinfo=timezone.utc)


async def sources_present(session: AsyncSession) -> List[str]:
    return [r[0] for r in (await session.execute(select(Observation.source).distinct().order_by(Observation.source))).all()]


async def _stats(session: AsyncSession, source: str) -> Dict[str, Any]:
    o = Observation
    n, zeros, neg, vmin, vmax, nst, first, last = (await session.execute(
        select(func.count(), func.coalesce(func.sum(case((o.value_mm == 0, 1), else_=0)), 0), func.coalesce(func.sum(case((o.value_mm < 0, 1), else_=0)), 0),
               func.min(o.value_mm), func.max(o.value_mm), func.count(func.distinct(o.station_key)), func.min(o.observed_at), func.max(o.observed_at))
        .where(o.source == source))).one()
    smallest_pos = (await session.execute(select(func.min(o.value_mm)).where(o.source == source, o.value_mm > 0))).scalar_one()
    codes = {}
    for c in CANDIDATE_MISSING_CODES:
        k = (await session.execute(select(func.count()).select_from(o).where(o.source == source, o.value_mm == c))).scalar_one()
        if k:
            codes[c] = int(k)
    return {"n": int(n), "zeros": int(zeros), "negatives": int(neg), "min": vmin, "max": vmax, "stations": int(nst), "first": first, "last": last,
            "smallest_positive": smallest_pos, "codes_present": codes}


async def _cadence(session: AsyncSession, source: str) -> Dict[str, Any]:
    o = Observation
    keys = [r[0] for r in (await session.execute(select(o.station_key).where(o.source == source).distinct().order_by(o.station_key).limit(SAMPLE_STATIONS))).all()]
    diffs: List[float] = []
    pairs_vals: List[tuple] = []
    for k in keys:
        rows = (await session.execute(select(o.observed_at, o.value_mm).where(o.source == source, o.station_key == k).order_by(o.observed_at)
                                      .limit(SAMPLE_PER_STATION))).all()
        for (t1, v1), (t2, v2) in zip(rows, rows[1:]):
            m = (_utc(t2) - _utc(t1)).total_seconds() / 60.0
            diffs.append(m)
            pairs_vals.append((m, float(v1), float(v2)))
    if not diffs:
        return {"median_minutes": None, "regular": False, "pairs": 0, "smooth_ratio": None, "sampled_stations": len(keys)}
    med = statistics.median(diffs)
    share = sum(1 for d in diffs if abs(d - med) < 1e-6) / len(diffs)
    steady = [(a, b) for m, a, b in pairs_vals if abs(m - med) < 1e-6]
    ratio = None
    if len(steady) >= MIN_PAIRS:
        vals = [a for a, _ in steady] + [steady[-1][1]]
        sd = statistics.pstdev(vals)
        if sd > 0:
            ratio = statistics.median(abs(b - a) for a, b in steady) / sd
    return {"median_minutes": float(med), "regular": share >= REGULAR_SHARE, "pairs": len(diffs), "share_at_median": round(share, 3),
            "smooth_ratio": ratio, "sampled_stations": len(keys)}


async def get_overrides(session: AsyncSession, source: str) -> Dict[str, Any]:
    row = await session.get(PipelineProfile, source)
    return dict(row.overrides or {}) if row else {}


def _clean_overrides(o: Dict[str, Any]) -> Dict[str, Any]:
    """Validate an edit. Raises ValueError with the reason."""
    out: Dict[str, Any] = {}
    unknown = [k for k in o if k not in EDITABLE]
    if unknown:
        raise ValueError("these profile fields cannot be edited: " + ", ".join(sorted(unknown)) + " (editable: " + ", ".join(EDITABLE) + ")")
    if o.get("parameter") is not None:
        p = str(o["parameter"]).strip().lower()
        if not p or len(p) > 40:
            raise ValueError("parameter must be 1 to 40 characters")
        out["parameter"] = p
    if o.get("kind") is not None:
        if o["kind"] not in KINDS:
            raise ValueError("kind must be one of " + ", ".join(KINDS))
        out["kind"] = o["kind"]
    if o.get("units") is not None:
        u = str(o["units"]).strip()
        if not u or len(u) > 20:
            raise ValueError("units must be 1 to 20 characters")
        out["units"] = u
    if "valid_range" in o:
        r = o["valid_range"]
        if r is not None:
            if not (isinstance(r, (list, tuple)) and len(r) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in r) and r[0] < r[1]):
                raise ValueError("valid_range must be [min, max] with min below max, or null for no range")
            r = [float(r[0]), float(r[1])]
        out["valid_range"] = r
    if "missing_codes" in o:
        c = o["missing_codes"]
        if c is None:
            c = []
        if not (isinstance(c, (list, tuple)) and len(c) <= 20 and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in c)):
            raise ValueError("missing_codes must be a list of at most 20 numbers")
        out["missing_codes"] = [float(x) for x in c]
    return out


async def save_overrides(session: AsyncSession, source: str, edits: Dict[str, Any]) -> Dict[str, Any]:
    """Merge validated edits into the stored overrides (a null value removes that override)."""
    new = _clean_overrides(edits)
    row = await session.get(PipelineProfile, source)
    cur = dict(row.overrides or {}) if row else {}
    for k, v in new.items():
        if v is None and k in ("kind", "units", "parameter"):
            cur.pop(k, None)
        else:
            cur[k] = v
    if row is None:
        session.add(PipelineProfile(source=source, overrides=cur))
    else:
        row.overrides = cur
        row.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return cur


async def get_profile(session: AsyncSession, source: str) -> Dict[str, Any]:
    st = await _stats(session, source)
    cad = await _cadence(session, source)
    ov = await get_overrides(session, source)
    mod = source_module(source)
    evidence: List[str] = []
    notes: List[str] = []
    n = st["n"]
    if n == 0:
        evidence.append(f"no stored observations for source {source!r}: nothing to detect from")
    else:
        evidence.append(f"{n:,} stored values from {st['stations']} station(s), {_utc(st['first']).date()} to {_utc(st['last']).date()}")

    # parameter
    param, p_src = "unknown", "not stated by the importer or the user"
    mp = getattr(mod, "PARAMETER", None) if mod is not None else None
    if isinstance(mp, str) and mp:
        param, p_src = mp.lower(), "stated by the importer"
    if "parameter" in ov:
        param, p_src = ov["parameter"], "edited by the user"
    defaults = PARAMETER_DEFAULTS.get(param, {})

    # zeros: data-detected, importer flag compared
    zero_share = (st["zeros"] / n) if n else None
    reports_zero = st["zeros"] > 0
    if n:
        if reports_zero:
            evidence.append(f"{st['zeros']:,} of {n:,} values are exactly zero ({zero_share:.1%}): the dataset reports zero values")
        else:
            sp = st["smallest_positive"]
            evidence.append(f"no zero values among {n:,}; the smallest value is {st['min']:g}" + (f" (smallest above zero: {sp:g})" if sp is not None else "")
                            + ": zeros appear to be omitted, so a missing step may be a zero step")
    flag = module_flag(source)
    if flag is not None and n and flag == reports_zero:      # flag says omits (True) but data has zeros, or flag says reports (False) but none present
        evidence.append(f"disagreement: the importer declares omits_zero_values={flag} but the data show {st['zeros']:,} zero values; the data-detected "
                        "result is used")
    elif flag is not None and n:
        evidence.append(f"the importer's own flag (omits_zero_values={flag}) agrees with the data")

    # cadence
    if cad["median_minutes"] is None:
        evidence.append("cadence unknown: fewer than two consecutive values per station")
    else:
        evidence.append(f"median interval {cad['median_minutes']:g} min over {cad['pairs']:,} consecutive pairs ({cad['sampled_stations']} station(s) sampled); "
                        f"{cad.get('share_at_median', 0):.0%} of intervals equal it, so the cadence is {'regular' if cad['regular'] else 'NOT regular'}")

    # kind
    kind, k_src = "unknown", "not enough evidence"
    if "kind" in ov:
        kind, k_src = ov["kind"], "edited by the user"
    elif defaults.get("kind"):
        kind, k_src = defaults["kind"], f"registered default for parameter {param!r}"
    elif 0 < n < MIN_VALUES:
        k_src = f"only {n} value(s), fewer than {MIN_VALUES}: too few to judge the kind"
    elif n:
        sr = cad.get("smooth_ratio")
        if zero_share is not None and zero_share >= ZERO_SHARE_INTERMITTENT:
            kind, k_src = "intermittent_accumulation", f"{zero_share:.0%} of values are zero"
        elif sr is not None and sr < SMOOTH_RATIO and cad["regular"]:
            kind, k_src = "continuous_state", f"values change smoothly between steps (median step change is {sr:.2f} of the standard deviation, below {SMOOTH_RATIO})"
        else:
            k_src = "values are neither mostly zero nor smooth between steps (or there are too few regular pairs), so the kind is not judged"
    evidence.append(f"kind {kind}: {k_src}")
    if kind == "unknown":
        notes.append("kind unknown: edit the profile (kind and parameter) so the right cleaning defaults apply; until then no gap filling is done")

    units = ov.get("units") or (getattr(mod, "UNITS", None) if mod is not None else None) or defaults.get("units")
    if "valid_range" in ov:
        vr = ov["valid_range"]
    else:
        vr = defaults.get("valid_range")
    if not units:
        notes.append("units not stated: edit the profile; values are used as stored")
    if vr is None:
        notes.append("no valid range known: nothing is excluded by range until you set one")
    elif "valid_range" not in ov and defaults.get("range_note"):
        notes.append("valid range: " + defaults["range_note"])
    notes.append(GENERATED_ONLY_NOTE)
    if param != RAINFALL:
        notes.append(verdict_status(param)["note"])
    codes = ov.get("missing_codes", [])
    if st["codes_present"]:
        listed = ", ".join(f"{c:g} ({k:,} times)" for c, k in st["codes_present"].items())
        evidence.append(f"values that look like missing-value codes are present: {listed}; they are treated as missing only if you add them to missing_codes")
    if st["negatives"]:
        evidence.append(f"{st['negatives']:,} negative value(s) present")
    return {"source": source, "parameter": param, "parameter_basis": p_src, "kind": kind, "reports_zero_values": bool(reports_zero) if n else False,
            "cadence": {"median_minutes": cad["median_minutes"], "regular": bool(cad["regular"])}, "units": units, "valid_range": vr, "missing_codes": codes,
            "edited_fields": sorted(ov), "evidence": evidence, "notes": notes, "n_values": n, "n_zero": st["zeros"],
            "n_negative": st["negatives"], "importer_flag_omits_zero_values": flag,
            "verdicts": verdict_status(param)}


def verdict_status(parameter: str) -> Dict[str, Any]:
    ok = parameter == RAINFALL
    return {"available": ok, "note": ("validation verdicts exist for rainfall" if ok else
            f"this dataset's parameter is {parameter!r}: it is explored and cleaned, but the platform does NOT claim validation verdicts "
            "(the checks and their evaluation exist for rainfall only)")}


def default_policy(profile: Dict[str, Any]) -> Dict[str, Any]:
    """The default cleaning policy a profile implies. 'Allowed' is not 'recommended': only a continuous state is filled by default."""
    kind, zeros = profile["kind"], profile["reports_zero_values"]
    if kind == "continuous_state":
        method, rule, why = "linear", "continuous-state-linear", "a continuous variable changes smoothly, so short gaps are filled by linear interpolation (imputed, labelled derived)"
    elif kind == "intermittent_accumulation" and zeros:
        method, rule, why = "none", "intermittent-reports-zeros-no-fill", ("this variable is intermittent (rain is not smooth); zeros are reported, so a missing value is a real "
                                                                           "gap and stays missing and flagged. Linear fill can be switched on, labelled imputed")
    elif kind == "intermittent_accumulation":
        method, rule, why = "none", "intermittent-omits-zeros-no-fill", ("this dataset has no zero values, so a missing step may be a dry step and filling would invent "
                                                                         "rain; filling is refused unless an explicit override_reason is recorded")
    else:
        method, rule, why = "none", "unknown-kind-no-fill", "the kind of this variable is not known, so nothing is filled; edit the profile first"
    steps: List[Dict[str, Any]] = [{"step": "remove_duplicates"}, {"step": "normalise_units", "from": profile.get("units"), "to": profile.get("units")}]
    vr = profile.get("valid_range")
    if vr or profile.get("missing_codes"):
        s: Dict[str, Any] = {"step": "exclude_out_of_range", "min": vr[0] if vr else None, "max": vr[1] if vr else None}
        steps.append(s)
    steps.append({"step": "fill_gaps", "method": method, "max_gap_steps": 3})
    return {"steps": steps, "rule": rule, "why": why, "basis": "default derived from the profile; maximum gap 3 steps is an assumed design choice (the owner has not set one)"}
