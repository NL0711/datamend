"""The Explore assistant: the Explainer seam applied to questions about the imported data.

* ``BaselineAssistant`` is rule based: it matches keywords to an intent, runs the matching table query on the stored data and writes the reply from the
  counts that query returned (so no number is typed in by hand). It always works.
* When a narrator is configured (NARRATOR_URL) the same question is forwarded through the existing narrator client (validation/narrate.py ->
  validation/explain.py NarratorExplainer); the narrator only adds wording. With none configured the reply says so plainly.

The assistant ADVISES. It never changes data, verdicts, scores or labels, and it never invents a number: ``table_spec`` is a query the user can run,
``cleaning.plan_hint`` is a suggestion the user must send themselves, and every reply is generated text, labelled so.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.pipeline import explore, profile as profile_svc
from backend.app.pipeline.models import Observation
from backend.app.validation import narrate
from backend.app.validation.explain import NarratorUnavailable

LABEL = "generated, not a decision"
NOT_CONNECTED = "AI narrator not connected: this is the rule-based assistant"
INTENTS = [   # order matters: the first intent with a matching keyword wins
    ("cleaning", ("clean", "interpolat", "fix gap", "fill", "impute", "best approach", "tidy")),
    ("unlocated", ("unlocated", "without coordinates", "no coordinates", "missing coordinates", "not located")),
    ("stations", ("station", "location", "map", "coordinates")),
    ("suspicious", ("negative", "suspicious", "impossible", "outlier", "invalid", "wrong value", "bad value", "out of range")),
    ("gaps", ("gap", "missing", "hours missing", "not reported")),
    ("wettest", ("wettest", "most rain", "highest", "largest", "biggest", "top days", "peak")),
    ("describe", ("describe", "summar", "overview", "what is in", "what's in", "tell me about", "my data")),
]


def detect_intent(message: str) -> (str, List[str]):
    m = message.lower()
    for name, words in INTENTS:
        hit = [w for w in words if w in m]
        if hit:
            return name, hit
    return "describe", []


class BaselineAssistant:
    generator = "baseline-rules"

    async def answer(self, session: AsyncSession, message: str, run_id: Optional[int] = None) -> Dict[str, Any]:
        intent, words = detect_intent(message)
        sources = await profile_svc.sources_present(session)
        why = [f"matched the intent '{intent}'" + (f" from the word(s): {', '.join(words)}" if words else " (no keyword matched, so the data summary is shown)"),
               "every number below comes from the query in table_spec, run just now on the stored data",
               "the assistant only reads: it changed no data, verdict, score or label"]
        if not sources:
            return {"reply": "There is no imported data yet: import a file first, then ask again.", "table_spec": None, "cleaning": None, "why": why, "intent": intent}
        m = message.lower()
        src = next((s for s in sources if s.lower() in m), None)
        if src is None:
            counts = {s: (await session.execute(select(func.count()).select_from(Observation).where(Observation.source == s))).scalar_one() for s in sources}
            src = max(sources, key=lambda s: counts[s])
        prof = await profile_svc.get_profile(session, src)
        u = f" {prof['units']}" if prof.get("units") else ""
        fn = getattr(self, "_" + intent)
        reply, spec, cleaning_hint = await fn(session, src, prof, u, run_id, why)
        if len(sources) > 1:
            why.append(f"the data of source {src!r} was used (other sources: {', '.join(s for s in sources if s != src)}); name a source in the question to pick another")
        return {"reply": reply, "table_spec": spec, "cleaning": cleaning_hint, "why": why, "intent": intent}

    # ---- intents: each returns (reply, table_spec, cleaning_hint)
    async def _describe(self, session, src, prof, u, run_id, why):
        spec = {"table": "station_summary", "order_by": [{"column": "n_observations", "dir": "desc"}], "limit": 20}
        r = await explore.run_query(session, spec)
        n_st = (await explore.run_query(session, {"table": "stations", "aggregates": [{"fn": "count", "as": "n"}]}))["rows"][0][0]
        reply = (f"Source {src}: {prof['n_values']:,} stored values from {r['total']} station(s) that reported. Parameter: {prof['parameter']}"
                 f"{' (' + prof['units'] + ')' if prof.get('units') else ''}; kind: {prof['kind']}. " + " ".join(prof["evidence"][:3]) +
                 f" The table lists the stations with the most values ({n_st} station(s) are known in all).")
        return reply, spec, None

    async def _stations(self, session, src, prof, u, run_id, why):
        v = await explore.stations_view(session)
        spec = {"table": "stations", "order_by": [{"column": "located", "dir": "desc"}, {"column": "station_key", "dir": "asc"}], "limit": 100}
        return (f"{len(v['stations'])} station(s) are known: {v['located']} located (valid coordinates in the file) and {v['unlocated']} unlocated. "
                "Unlocated stations are never placed by guessing; the Stations view shows the located ones on the map."), spec, None

    async def _unlocated(self, session, src, prof, u, run_id, why):
        spec = {"table": "stations", "filters": [{"column": "located", "op": "=", "value": False}], "limit": 100}
        r = await explore.run_query(session, spec)
        reply = (f"{r['total']} station(s) have no valid coordinates and cannot be placed on the map." if r["total"] else
                 "Every known station has valid coordinates.") + " Coordinates are never guessed: add them to the source file and import again."
        return reply, spec, None

    async def _gaps(self, session, src, prof, u, run_id, why):
        if not prof["cadence"]["regular"]:
            med = prof["cadence"]["median_minutes"]
            return (f"Gaps cannot be counted for {src}: its reporting interval is not regular"
                    f"{'' if med is None else f' (median {med:g} min)'}, so the platform cannot tell what a missing step is. "
                    + ("This dataset has no zero values, so a missing step may simply be a dry step. " if not prof["reports_zero_values"] else "")
                    + "The table lists the stations and how many values each has."), {"table": "station_summary", "order_by": [{"column": "n_observations", "dir": "desc"}], "limit": 50}, None
        spec = {"table": "gaps", "order_by": [{"column": "missing_steps", "dir": "desc"}], "limit": 50}
        r = await explore.run_query(session, spec)
        allowed = await explore.run_query(session, {"table": "gaps", "filters": [{"column": "interpolation_allowed", "op": "=", "value": True}],
                                                    "aggregates": [{"fn": "count", "as": "n"}]})
        worst = r["rows"][0][4] if r["rows"] else 0
        return (f"{r['total']} gap(s) between consecutive reported values (expected step {prof['cadence']['median_minutes']:g} min); the longest is {worst} missing "
                f"step(s). The profile would permit filling {allowed['rows'][0][0]} of them, but permitted is not recommended: see the cleaning advice for this data."), spec, None

    async def _wettest(self, session, src, prof, u, run_id, why):
        spec = {"table": "daily", "order_by": [{"column": "mm", "dir": "desc"}], "limit": 10}
        r = await explore.run_query(session, spec)
        if not r["rows"]:
            return "There are no daily totals yet.", spec, None
        top = r["rows"][0]
        return (f"The largest daily total is {top[3]:g}{u} at station {top[0]} on {top[2]} ({top[5]} reported step(s), largest single step {top[6]:g}{u}). "
                f"The table lists the top 10 of {r['total']:,} station-days. A large value is not by itself a fault."), spec, None

    async def _suspicious(self, session, src, prof, u, run_id, why):
        vr = prof.get("valid_range")
        lo, hi = (vr[0], vr[1]) if vr else (0.0, None)
        neg = (await explore.run_query(session, {"table": "hourly", "filters": [{"column": "source", "op": "=", "value": src}, {"column": "mm", "op": "<", "value": lo}],
                                                 "limit": 1}))["total"]
        high = 0
        if hi is not None:
            high = (await explore.run_query(session, {"table": "hourly", "filters": [{"column": "source", "op": "=", "value": src}, {"column": "mm", "op": ">", "value": hi}],
                                                      "limit": 1}))["total"]
        if high and not neg:
            spec = {"table": "hourly", "filters": [{"column": "source", "op": "=", "value": src}, {"column": "mm", "op": ">", "value": hi}],
                    "order_by": [{"column": "mm", "dir": "desc"}], "limit": 50}
        else:
            spec = {"table": "hourly", "filters": [{"column": "source", "op": "=", "value": src}, {"column": "mm", "op": "<", "value": lo}],
                    "order_by": [{"column": "mm", "dir": "asc"}], "limit": 50}
        reply = (f"{neg:,} stored value(s) are below {lo:g}{u}" + (f" and {high:,} are above {hi:g}{u}" if hi is not None else "") +
                 (" (the range comes from the dataset profile)." if vr else " (no valid range is set in the profile, so only values below zero were counted).") +
                 " The table shows the " + ("values above the range." if high and not neg else "values below the range.") +
                 " These are candidates for exclusion in the cleaning plan, not verdicts.")
        if run_id is not None:
            f = await explore.run_query(session, {"table": "flags", "run_id": run_id, "aggregates": [{"fn": "count", "as": "n"}]})
            reply += f" Check run {run_id} flagged {f['rows'][0][0]} station-day(s) (flags table)."
        return reply, spec, None

    async def _cleaning(self, session, src, prof, u, run_id, why):
        from backend.app.pipeline import cleaning
        default = profile_svc.default_policy(prof)
        n, z = prof["n_values"], prof["n_zero"]
        lines = [f"Best cleaning for {src} ({prof['parameter']}, kind {prof['kind']}):"]
        lines.append(f"{z:,} of {n:,} values are zero" + (f" ({z / n:.1%})" if n else "") + (": zeros are reported." if z else ": zeros are omitted."))
        gap_count = None
        if prof["cadence"]["regular"]:
            gap_count = (await explore.run_query(session, {"table": "gaps", "aggregates": [{"fn": "count", "as": "n"}, {"fn": "max", "column": "missing_steps", "as": "longest"}],
                                                           "filters": [{"column": "source", "op": "=", "value": src}]}))["rows"][0]
            lines.append(f"Cadence is regular ({prof['cadence']['median_minutes']:g} min); {gap_count[0]} gap(s), the longest {gap_count[1] or 0} missing step(s).")
        else:
            lines.append("The reporting interval is not regular, so gaps cannot be measured.")
        vr = prof.get("valid_range")
        if vr:
            out_n = sum((await explore.run_query(session, {"table": "hourly", "limit": 1, "filters": [{"column": "source", "op": "=", "value": src}, {"column": "mm", "op": op, "value": v}]}))["total"]
                        for op, v in (("<", vr[0]), (">", vr[1])))
            lines.append(f"{out_n:,} value(s) lie outside the profile's valid range {vr[0]:g} to {vr[1]:g}{u}.")
        rule = default["rule"]
        fill = next(s for s in default["steps"] if s["step"] == "fill_gaps")["method"]
        lines.append(f"Rule applied: {rule}. " + default["why"] + ".")
        lines.append("Suggested policy: " + ", ".join(s["step"] + (f"({s['method']}, up to {s['max_gap_steps']} steps)" if s["step"] == "fill_gaps" else "") for s in default["steps"])
                     + ". This is advice only: nothing was changed. Send the policy to the cleaning plan to create proposals you can accept or reject; filled values are labelled imputed.")
        if fill == "none":
            lines.append("Gaps are left missing and flagged.")
        why.append(f"cleaning rule '{rule}' chosen from the profile (kind={prof['kind']}, reports_zero_values={prof['reports_zero_values']})")
        spec = ({"table": "gaps", "filters": [{"column": "source", "op": "=", "value": src}], "order_by": [{"column": "missing_steps", "dir": "desc"}], "limit": 50}
                if prof["cadence"]["regular"] else {"table": "station_summary", "order_by": [{"column": "n_observations", "dir": "desc"}], "limit": 50})
        hint = {"plan_hint": {"endpoint": "POST /api/pipeline/clean/plan", "body": {"source": src, "policy": {"steps": [{k: v for k, v in s.items()} for s in default["steps"]]}}},
                "rule": rule, "profile": {k: prof[k] for k in ("parameter", "kind", "reports_zero_values", "cadence", "units", "valid_range")}, "advice_only": True,
                "verdicts": prof["verdicts"]}
        if not prof["verdicts"]["available"]:
            lines.append(prof["verdicts"]["note"] + ".")
        return " ".join(lines), spec, hint


async def respond(session: AsyncSession, message: str, history: Optional[List[Dict[str, str]]] = None, run_id: Optional[int] = None) -> Dict[str, Any]:
    base = await BaselineAssistant().answer(session, message, run_id)
    out = {"reply": base["reply"], "generator": "baseline-rules", "generated": True, "label": LABEL, "table_spec": base["table_spec"], "cleaning": base["cleaning"],
           "why": base["why"]}
    narrator = narrate.get_narrator()
    if narrator is None:
        out["reply"] += " " + NOT_CONNECTED + "."
        out["why"].append(NOT_CONNECTED)
        return out
    ctx = {"assistant": "explore", "advice_only": True, "intent": base["intent"], "facts": base["reply"], "table_spec": base["table_spec"],
           "history": [{"role": h["role"], "text": h["text"][:300]} for h in (history or [])[-6:]]}
    try:
        ex = await narrator.explain(None, question=message, kind="chat", context=ctx)
    except NarratorUnavailable as e:
        out["reply"] += f" The AI narrator did not answer ({e}): this is the rule-based assistant."
        out["why"].append(f"narrator configured but unavailable: {e}")
        return out
    out.update(reply=ex.text, generator="mcp-narrator")
    out["why"].append("the wording is the AI narrator's (generated); the table_spec and the counts it was given come from the rule-based queries")
    return out
