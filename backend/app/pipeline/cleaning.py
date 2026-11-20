"""Cleaning as a configurable POLICY driven by the dataset's variable profile (pipeline/profile.py).

A policy is an ordered list of steps with parameters (stored with every plan, so a result can be reproduced):

* ``remove_duplicates``: the raw store keeps one value per source, station and step (a second ingest skips duplicates), so this finds nothing to remove.
* ``normalise_units`` ``{from, to}``: equal units are a no-op; a conversion is NOT IMPLEMENTED (it would rewrite every value) and is refused with the reason.
* ``exclude_out_of_range`` ``{min, max}``: values outside the range (default: the profile's valid range) and values equal to a profile missing-value code
  become ``exclude`` proposals ("treat as no data"). Must come before ``fill_gaps``.
* ``fill_gaps`` ``{method: none|linear|previous, max_gap_steps (1..6, default 3), override_reason}``: fills the missing steps INSIDE a gap, between
  the nearest reported values on both sides, never before the first or after the last value, only gaps of at most ``max_gap_steps`` missing steps.

Rules that cannot be switched off silently:
1. Raw observations are never changed. Proposals live in ``pipeline_cleaning``; an accepted one is applied only to a check run made with ``use_clean``.
2. A dataset whose profile says zeros are omitted (or whose kind is unknown) is NOT filled: the fill step is refused unless ``override_reason`` is recorded;
   the override reason is stored in the plan and in every proposal's ``why``.
3. Filled values are ``basis: derived`` (imputed) wherever they appear.
4. Every refusal is returned in ``skipped`` with the plain reason.
The planner reads only the profile (units, range, missing codes, cadence, kind); it holds no parameter-specific rule.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.pipeline import profile as profile_svc
from backend.app.pipeline.models import CleaningPlan, Observation, PipelineCleaning

STEPS = {"remove_duplicates": (), "normalise_units": ("from", "to"), "exclude_out_of_range": ("min", "max", "missing_codes"),
         "fill_gaps": ("method", "max_gap_steps", "override_reason")}
METHODS = ("none", "linear", "previous")
DEFAULT_GAP, MAX_GAP = 3, 6
MAX_PROPOSALS = 20000
SHOW = 200
OMITS_ZERO_REASON = ("this dataset has no zero values (the source lists only non-zero values), so a missing step may be a dry step; filling would invent "
                     "rain: refused unless an explicit override_reason is recorded")
UNKNOWN_KIND_REASON = "the kind of this variable is unknown, so filling is refused unless an explicit override_reason is recorded (edit the profile first)"


class PolicyError(ValueError):
    pass


def _utc(t: datetime) -> datetime:
    return t if t.tzinfo is not None else t.replace(tzinfo=timezone.utc)


def _iso(t: datetime) -> str:
    return _utc(t).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_policy(policy: Any) -> Dict[str, Any]:
    """The policy in normal form, or PolicyError (an API 400) naming the problem."""
    if not isinstance(policy, dict) or not isinstance(policy.get("steps"), list) or not policy["steps"]:
        raise PolicyError("policy must be an object with a non-empty 'steps' list")
    if len(policy["steps"]) > 10:
        raise PolicyError("a policy has at most 10 steps")
    seen: List[str] = []
    out: List[Dict[str, Any]] = []
    for s in policy["steps"]:
        if not isinstance(s, dict) or s.get("step") not in STEPS:
            raise PolicyError("each step needs 'step' as one of " + ", ".join(STEPS))
        name = s["step"]
        if name in seen:
            raise PolicyError(f"step {name!r} appears twice")
        extra = [k for k in s if k != "step" and k not in STEPS[name]]
        if extra:
            raise PolicyError(f"step {name!r} has unknown parameter(s): " + ", ".join(sorted(extra)))
        n: Dict[str, Any] = {"step": name}
        if name == "normalise_units":
            for k in ("from", "to"):
                v = s.get(k)
                if v is not None and (not isinstance(v, str) or len(v) > 20):
                    raise PolicyError(f"normalise_units.{k} must be a short text")
                n[k] = v
        elif name == "exclude_out_of_range":
            for k in ("min", "max"):
                v = s.get(k)
                if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)):
                    raise PolicyError(f"exclude_out_of_range.{k} must be a number or null")
                n[k] = None if v is None else float(v)
            if n["min"] is not None and n["max"] is not None and n["min"] >= n["max"]:
                raise PolicyError("exclude_out_of_range: min must be below max")
            n["missing_codes"] = bool(s.get("missing_codes", True))
        elif name == "fill_gaps":
            m = s.get("method", "none")
            if m not in METHODS:
                raise PolicyError("fill_gaps.method must be one of " + ", ".join(METHODS))
            g = s.get("max_gap_steps", DEFAULT_GAP)
            if isinstance(g, bool) or not isinstance(g, int) or not 1 <= g <= MAX_GAP:
                raise PolicyError(f"fill_gaps.max_gap_steps must be a whole number from 1 to {MAX_GAP}")
            r = s.get("override_reason")
            if r is not None and (not isinstance(r, str) or len(r) > 300):
                raise PolicyError("override_reason must be text of at most 300 characters")
            n.update(method=m, max_gap_steps=g)
            if r is not None:
                n["override_reason"] = r
        seen.append(name)
        out.append(n)
    if "fill_gaps" in seen and "exclude_out_of_range" in seen and seen.index("exclude_out_of_range") > seen.index("fill_gaps"):
        raise PolicyError("exclude_out_of_range must come before fill_gaps (an impossible value must not be used as a neighbour)")
    return {"steps": out}


def policy_from_legacy(default: Dict[str, Any], method: Optional[str], max_gap: Optional[int]) -> Dict[str, Any]:
    """The first contract's {method, max_gap_hours} mapped onto a policy: auto = the profile default, exclude = no fill, linear = linear fill."""
    steps = [dict(s) for s in default["steps"]]
    for s in steps:
        if s["step"] == "fill_gaps":
            if method == "exclude":
                s["method"] = "none"
            elif method == "linear":
                s["method"] = "linear"
            if max_gap is not None:
                s["max_gap_steps"] = max_gap
    return {"steps": steps}


def fill_decision(profile: Dict[str, Any], step: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
    """(allowed, refusal_reason, override_used) for a fill_gaps step against a profile."""
    if step["method"] == "none":
        return False, None, None
    reason = None
    if profile["kind"] == "intermittent_accumulation" and not profile["reports_zero_values"]:
        reason = OMITS_ZERO_REASON
    elif profile["kind"] == "unknown":
        reason = UNKNOWN_KIND_REASON
    if reason is None:
        return True, None, None
    ov = (step.get("override_reason") or "").strip()
    if len(ov) < 10:
        return False, reason + (" (an override_reason was sent but is too short: give at least 10 characters saying why)" if step.get("override_reason") is not None else ""), None
    return True, None, ov


def _step_minutes(profile: Dict[str, Any]) -> Optional[float]:
    c = profile.get("cadence") or {}
    return float(c["median_minutes"]) if c.get("regular") and c.get("median_minutes") else None


def prop_dict(p: PipelineCleaning) -> Dict[str, Any]:
    return {"id": p.id, "plan_id": p.plan_id, "source": p.source, "station_key": p.station_key, "at": _iso(p.at), "kind": p.kind, "original": p.original,
            "proposed": p.proposed, "method": p.method, "why": p.why, "neighbours": p.neighbours, "basis": p.basis, "status": p.status,
            "label": "imputed (derived), not measured" if p.kind == "interpolate" else "excluded as impossible (the original is kept)"}


async def plan(session: AsyncSession, source: str, policy: Optional[Dict[str, Any]] = None, method: Optional[str] = None,
               max_gap: Optional[int] = None) -> Dict[str, Any]:
    prof = await profile_svc.get_profile(session, source)
    default = profile_svc.default_policy(prof)
    if policy is None:
        pol = validate_policy(policy_from_legacy(default, method, max_gap) if (method or max_gap) else default)
        used_default = not (method or max_gap)
    else:
        pol, used_default = validate_policy(policy), False
    skipped: Dict[Tuple[str, str], int] = {}
    steps_report: List[Dict[str, Any]] = []

    def skip(station: str, reason: str, count: int = 1) -> None:
        skipped[(station, reason)] = skipped.get((station, reason), 0) + count

    ex_step = fill_step = None
    for s in pol["steps"]:
        if s["step"] == "remove_duplicates":
            steps_report.append({"step": "remove_duplicates", "applied": 0, "note": "the raw store keeps one value per source, station and step, so there is nothing to remove"})
        elif s["step"] == "normalise_units":
            a, b = s.get("from"), s.get("to")
            if a == b or a is None or b is None:
                steps_report.append({"step": "normalise_units", "applied": 0, "note": "units already match (or are not stated): nothing converted"})
            else:
                r = f"unit conversion from {a} to {b} is NOT IMPLEMENTED (it would rewrite every stored value); correct the units when importing, or edit the profile's units"
                steps_report.append({"step": "normalise_units", "applied": 0, "note": r})
                skip("*", r, 1)
        elif s["step"] == "exclude_out_of_range":
            ex_step = s
        elif s["step"] == "fill_gaps":
            fill_step = s

    lo = hi = None
    codes: List[float] = []
    if ex_step is not None:
        lo = ex_step["min"] if ex_step["min"] is not None else None
        hi = ex_step["max"] if ex_step["max"] is not None else None
        if ex_step["min"] is None and ex_step["max"] is None and prof.get("valid_range"):
            lo, hi = prof["valid_range"]
        if ex_step["missing_codes"]:
            codes = list(prof.get("missing_codes") or [])
    allowed, refusal, override = (False, None, None)
    step_min = _step_minutes(prof)
    if fill_step is not None:
        allowed, refusal, override = fill_decision(prof, fill_step)
        if refusal:
            skip("*", refusal, 1)
            steps_report.append({"step": "fill_gaps", "applied": 0, "note": "refused: " + refusal})
        elif fill_step["method"] == "none":
            steps_report.append({"step": "fill_gaps", "applied": 0, "note": "method none: gaps stay missing (rule: " + default["rule"] + ")" if used_default else "method none: gaps stay missing"})
        elif step_min is None:
            allowed = False
            r = "the cadence of this dataset is not regular (or unknown), so the length of a gap in steps cannot be told; nothing filled"
            skip("*", r, 1)
            steps_report.append({"step": "fill_gaps", "applied": 0, "note": "refused: " + r})

    row = CleaningPlan(source=source, policy=pol, profile=_jsonable(prof), summary={})
    session.add(row)
    await session.flush()
    existing = {(r[0], _utc(r[1]), r[2]) for r in (await session.execute(select(PipelineCleaning.station_key, PipelineCleaning.at, PipelineCleaning.kind)
                                                                        .where(PipelineCleaning.source == source))).all()}
    keys = [r[0] for r in (await session.execute(select(Observation.station_key).where(Observation.source == source).distinct().order_by(Observation.station_key))).all()]
    created: List[PipelineCleaning] = []
    n_excl = n_fill = 0
    param, units = prof["parameter"], prof.get("units") or ""
    u = f" {units}" if units else ""
    capped = False

    def add(p: PipelineCleaning) -> bool:
        nonlocal capped
        if (p.station_key, _utc(p.at), p.kind) in existing:
            skip(p.station_key, "already proposed (same station, time and kind)")
            return False
        if len(created) >= MAX_PROPOSALS:
            capped = True
            return False
        created.append(p)
        existing.add((p.station_key, _utc(p.at), p.kind))
        return True

    for k in keys:
        rows = (await session.execute(select(Observation.observed_at, Observation.value_mm).where(Observation.source == source, Observation.station_key == k)
                                      .order_by(Observation.observed_at))).all()
        series = [(_utc(t), float(v)) for t, v in rows]
        bad = set()
        for i, (t, v) in enumerate(series):
            why = method_name = None
            if v in codes:
                why, method_name = f"the value {v:g} equals a missing-value code listed in the dataset profile; excluded (treated as no data)", "missing_code"
            elif (lo is not None and v < lo) or (hi is not None and v > hi):
                rng = f"{lo:g} to {hi:g}" if lo is not None and hi is not None else (f"at least {lo:g}" if lo is not None else f"at most {hi:g}")
                why, method_name = (f"the value {v:g}{u} is outside the valid range for {param} ({rng}{u}; range from the dataset profile or the policy); "
                                    "excluded (treated as no data)"), "range"
            if why:
                bad.add(i)
                nb = [{"at": _iso(series[j][0]), "value": series[j][1]} for j in (i - 1, i + 1) if 0 <= j < len(series)]
                if add(PipelineCleaning(plan_id=row.id, source=source, station_key=k, at=t, kind="exclude", original=v, proposed=None, method=method_name,
                                        why=why + ". The original value is kept; raw data is never changed.", neighbours=nb, basis="derived")):
                    n_excl += 1
        if not allowed:
            continue
        g = fill_step["max_gap_steps"]
        m = fill_step["method"]
        for i in range(len(series) - 1):
            (t1, v1), (t2, v2) = series[i], series[i + 1]
            d = (t2 - t1).total_seconds() / 60.0 / step_min
            if d < 1.5:
                continue
            miss = round(d) - 1
            if abs(d - round(d)) > 0.01:
                skip(k, f"the interval between two reported values is not a whole number of steps ({step_min:g} min); not filled", 1)
                continue
            if miss > g:
                skip(k, f"gap longer than max_gap_steps ({g}); left missing", miss)
                continue
            if i in bad or (i + 1) in bad:
                skip(k, "a neighbouring value is impossible (excluded), so nothing is filled across it", miss)
                continue
            for j in range(1, miss + 1):
                at = t1 + timedelta(minutes=step_min * j)
                val = round(v1 + (v2 - v1) * j / (miss + 1), 3) if m == "linear" else v1
                how = (f"linear interpolation in time between the two reported values gives {val:g}{u}" if m == "linear"
                       else f"the previous reported value ({v1:g}{u}) is carried forward")
                text = (f"{miss} step(s) of {step_min:g} min are missing between {_iso(t1)} ({v1:g}{u}) and {_iso(t2)} ({v2:g}{u}); {how} for {_iso(at)}. "
                        f"Method {m}; only gaps of at most {g} missing steps are filled and nothing is ever filled before the first or after the last reported value. "
                        "This value is imputed (derived), not measured; the raw data is unchanged.")
                if override:
                    text += f" OVERRIDE recorded: {override}"
                if add(PipelineCleaning(plan_id=row.id, source=source, station_key=k, at=at, kind="interpolate", original=None, proposed=val, method=m, why=text,
                                        neighbours=[{"at": _iso(t1), "value": v1}, {"at": _iso(t2), "value": v2}], basis="derived")):
                    n_fill += 1
    if capped:
        skip("*", f"plan limit of {MAX_PROPOSALS:,} proposals reached; the rest was not planned", 1)
    session.add_all(created)
    skipped_list = [{"station_key": a, "reason": b, "count": c} for (a, b), c in sorted(skipped.items())]
    row.summary = {"created": len(created), "interpolate": n_fill, "exclude": n_excl, "override_used": bool(override)}
    await session.commit()
    for p in created[:SHOW]:
        await session.refresh(p)
    steps_report.append({"step": "exclude_out_of_range", "applied": n_excl}) if ex_step is not None else None
    if fill_step is not None and allowed:
        steps_report.append({"step": "fill_gaps", "applied": n_fill, "method": fill_step["method"], "max_gap_steps": fill_step["max_gap_steps"],
                             "override_reason": override})
    return {"plan_id": row.id, "created": len(created), "interpolate": n_fill, "exclude": n_excl, "skipped": skipped_list, "policy": pol,
            "policy_source": "default derived from the profile" if used_default else "as sent", "default_rule": default["rule"], "profile": prof,
            "steps": steps_report, "proposals": [prop_dict(p) for p in created[:SHOW]], "proposals_shown": min(len(created), SHOW),
            "verdicts": prof["verdicts"]}


def _jsonable(d: Dict[str, Any]) -> Dict[str, Any]:
    import json
    return json.loads(json.dumps(d, default=str))


async def list_proposals(session: AsyncSession, status: str = "pending", station: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    q = select(PipelineCleaning)
    if status != "all":
        q = q.where(PipelineCleaning.status == status)
    if station:
        q = q.where(PipelineCleaning.station_key == station)
    rows = (await session.execute(q.order_by(PipelineCleaning.id).limit(max(1, min(limit, 1000))))).scalars().all()
    return [prop_dict(p) for p in rows]


async def decide(session: AsyncSession, pid: int, accept: bool, by: str = "admin") -> Dict[str, Any]:
    p = await session.get(PipelineCleaning, pid)
    if p is None:
        raise LookupError("no such cleaning proposal")
    if p.status != "pending":
        raise ValueError(f"the proposal is already {p.status}")
    p.status = "accepted" if accept else "rejected"
    p.decided_by, p.decided_at = by, datetime.now(timezone.utc)
    await session.commit()
    return prop_dict(p)


async def apply_summary(session: AsyncSession, source: Optional[str] = None, accept_pending: bool = False) -> Dict[str, Any]:
    """Optionally accept every pending proposal, then count what a ``use_clean`` check run will include. Changes no observation."""
    q = select(PipelineCleaning)
    if source:
        q = q.where(PipelineCleaning.source == source)
    rows = (await session.execute(q)).scalars().all()
    newly = 0
    if accept_pending:
        for p in rows:
            if p.status == "pending":
                p.status, p.decided_by, p.decided_at = "accepted", "admin (accept all)", datetime.now(timezone.utc)
                newly += 1
        await session.commit()
    acc = [p for p in rows if p.status == "accepted"]
    return {"source": source, "newly_accepted": newly, "accepted": len(acc), "imputed_values": sum(1 for p in acc if p.kind == "interpolate"),
            "excluded_values": sum(1 for p in acc if p.kind == "exclude"), "pending": sum(1 for p in rows if p.status == "pending"),
            "rejected": sum(1 for p in rows if p.status == "rejected"), "stations": len({p.station_key for p in acc}),
            "note": "no observation was changed; accepted proposals are used by a check run made with use_clean, and imputed values are labelled derived"}


async def load_accepted(session: AsyncSession, source: str) -> Dict[str, Dict[str, Any]]:
    """Accepted proposals of a source by station: {'fill': {time: value}, 'exclude': {time}}."""
    out: Dict[str, Dict[str, Any]] = {}
    rows = (await session.execute(select(PipelineCleaning).where(PipelineCleaning.source == source, PipelineCleaning.status == "accepted"))).scalars().all()
    for p in rows:
        d = out.setdefault(p.station_key, {"fill": {}, "exclude": set()})
        if p.kind == "interpolate" and p.proposed is not None:
            d["fill"][_utc(p.at)] = p.proposed
        elif p.kind == "exclude":
            d["exclude"].add(_utc(p.at))
    return out


async def accepted_meta(session: AsyncSession, source: str) -> Dict[str, Any]:
    rows = (await session.execute(select(PipelineCleaning).where(PipelineCleaning.source == source, PipelineCleaning.status == "accepted"))).scalars().all()
    ids = sorted({p.plan_id for p in rows if p.plan_id is not None})
    pols = []
    for i in ids:
        pl = await session.get(CleaningPlan, i)
        if pl is not None:
            pols.append({"plan_id": i, "policy": pl.policy})
    return {"accepted_proposals": len(rows), "plan_ids": ids, "policies": pols}
