"""The model card for the explainability step: how a flag is made, built from the real catalogue, the real registry and the real narrator setting.

Nothing is typed in that can drift: the checks and thresholds are read from ``validation/checks.py``, the champion from the registry table, the
narrator state from the same function the rest of the platform uses. What is NOT built is listed as such.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.pipeline.models import ModelVersion
from backend.app.validation import checks, narrate
from backend.app.validation import weather_checks as wx    # registers the temperature, pressure and humidity checks in the catalogue

NEIGHBOUR_NOTE = (f"needs {checks.MIN_NEIGHBOURS}+ stations with coordinates within {checks.NEIGHBOUR_RADIUS_KM:g} km; fires when at least "
                  f"{checks.NEIGHBOUR_AGREE:.0%} of them disagree")
THRESHOLD_NOTES = {
    "negative_value": "any value below 0",
    "intensity_above_ceiling": f"above {checks.INTENSITY_CEILING:g} mm per hour (assumed ceiling)",
    "counter_jump": f"counter increase of more than {checks.JUMP_MM:g} mm between consecutive readings",
    "counter_reset": "counter falls back (information only, no verdict change)",
    "frozen_intensity": f"{checks.FROZEN_N} identical non-zero intensities in a row",
    "intensity_counter_mismatch": f"intensity above 0 with a flat counter for {checks.MISMATCH_N} readings",
    "neighbour_isolated_wet": NEIGHBOUR_NOTE + " (this station wet, neighbours dry)",
    "neighbour_isolated_dry": NEIGHBOUR_NOTE + " (this station dry, neighbours wet)",
    "impossible_value": f"daily total above {checks.DAILY_MAX_MM:g} mm or below 0",
    "repeated_value": f"the same positive daily value on {checks.REPEAT_DAYS} consecutive complete days",
    "climatology_upper_tail": (f"upper-tail probability below {checks.CLIM_TAIL_P:g} on the gauge's own earlier wet days within {checks.CLIM_WINDOW_DAYS} days of the "
                               f"same day of year (needs {checks.CLIM_MIN_WET} earlier wet days); wet day = at least {checks.WET_DAY_MM:g} mm"),
    "duplicate_row": "the same station and time appears twice",
}
# temperature, pressure and humidity checks of the stream (all thresholds assumed, uncalibrated): the notes come from the module's own constants
THRESHOLD_NOTES.update({
    "corrupt_value": "a non-finite number or a sentinel such as 9999.9 or -999",
    "value_out_of_range": f"temperature outside {wx.HARD_BOUNDS['temperature']}, station pressure outside {wx.HARD_BOUNDS['pressure']} hPa, humidity outside {wx.HARD_BOUNDS['humidity']} %",
    "extreme_value": f"temperature outside {wx.EXTREME_TEMPERATURE} C: unconfirmed, UNCERTAIN only",
    "rate_of_change": "step between readings above a floor plus an allowance per minute of elapsed time (per variable)",
    "frozen_value": f"{wx.FROZEN_N} identical readings in a row spanning at least {wx.FROZEN_MIN_SPAN_S:g} s (not humidity at saturation)",
    "spike_vs_history": f"deviation from the station's recent robust level above {wx.SPIKE_K:g} robust sigmas and a physical minimum; UNCERTAIN when other variables move with it at a steady dew point",
    "level_shift": f"mean of the last 3 readings away from an earlier baseline ({wx.SHIFT_N - wx.SHIFT_RECENT_EXCLUDE} readings) by more than a limit that grows with elapsed time",
    "dewpoint_above_temperature": f"Magnus-Tetens dew point derived from temperature and humidity above the temperature by more than {wx.DEWPOINT_ABOVE_TEMPERATURE_C:g} C",
    "dewpoint_jump": f"derived dew point changes by more than {wx.DEWPOINT_STEP_C:g} C plus {wx.DEWPOINT_PER_MIN:g} C per minute",
    "dropout": f"a variable missing now that the station reported within its last {wx.DROPOUT_LOOKBACK} readings (never-reported variables are 'not run')",
    "reporting_gap": f"time since the previous reading above {wx.GAP_FACTOR:g} times the station's own cadence (and {wx.GAP_ABS_MIN_S:g} s)",
})

FLAGS_HOW = [
    "Fixed rules come first: impossible values, repeated values and similar integrity checks fire when a value breaks a stated limit.",
    "A statistic compares a heavy day with the gauge's own earlier wet days near the same time of year (an upper-tail test on a gamma fit).",
    "Neighbour votes compare a station with the stations around it: a station that is wet while its neighbours are dry (or the reverse) is marked uncertain.",
    "A size alone never makes a value a fault: a heavy value with no other fault check is UNCERTAIN, and neighbours reporting rain are recorded as corroboration.",
    "The rule score combines the checks that fired into a number from 0 to 1. It is an uncalibrated ordering of suspicion, NOT a probability.",
    "A trained model, if one is registered, may re-weight the checks offline; it never changes a verdict, and the platform does not score with it on the server.",
    "The explanation text is generated from the evidence, stored separately and marked generated; it never changes a verdict, score or evidence.",
]

NOT_IMPLEMENTED = [
    "scoring with a registered model on the server (needs RF25 grid neighbours)",
    "a calibrated probability: the rule score is uncalibrated and there are no real quality-control labels for India to calibrate against",
    "checks and verdicts for parameters other than rainfall (other parameters are explored and cleaned, but get no verdicts)",
    "unit conversion in the cleaning step",
    "the AI narrator itself (built by the AI implementation team; the rule-based baseline works without it)",
]


async def build(session: AsyncSession) -> Dict[str, Any]:
    cat: List[Dict[str, Any]] = []
    for name, c in checks.CATALOGUE.items():
        cat.append({"name": name, "profile": c.profile, "layer": c.layer, "kind": c.kind, "weight": c.weight, "needs": c.needs,
                    "threshold_note": THRESHOLD_NOTES.get(name, "")})
    m: Optional[ModelVersion] = (await session.execute(select(ModelVersion).where(ModelVersion.alias == "champion").order_by(ModelVersion.id.desc()))).scalars().first()
    champion = None
    if m is not None:
        art = (m.metrics or {}).get("artifact") or {}
        champion = {"id": m.id, "name": m.name, "version": m.version, "weights": art.get("weights"), "weight_checks": art.get("checks"),
                    "metrics_basis": "declared, not verified", "trained_from_snapshot": m.snapshot_id}
    narrator = narrate.get_narrator()
    st = narrate.narrator_status(narrator)
    return {"method": checks.METHOD, "checks": cat, "champion": champion,
            "explanation": {"generator": "mcp-narrator" if narrator is not None else "baseline-rules", "narrator_connected": narrator is not None,
                            "note": st["message"] + ("" if narrator is not None else ": explanations come from fixed rules over the evidence")},
            "flags_how": FLAGS_HOW, "not_implemented": NOT_IMPLEMENTED}
