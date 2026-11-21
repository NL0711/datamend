"""Pre-written demo answers for the Cloudburst-1 sample file (owner decision, 2026-11-21, a demo exception to AGENTS.md section 4).

Used ONLY when the language model is unavailable (no key, a bad key, a model error) and the station is one of the five stations of the
Cloudburst-1 sample (SYN-A to SYN-E). The text is written by hand from what the rule checks find in that file's intensity-only version; no model
wrote it. The Agent page shows it under the label "pre-written demo answer (no model)", never as a model answer.
"""
from __future__ import annotations

from typing import Optional

GENERATOR = "pre-written demo answer (no model)"

ANSWERS = {
    "SYN-A": ("At 15:00 UTC on 2026-07-01 station SYN-A reported a rain intensity of 380 mm/h. That is above the 300 mm/h physical ceiling used by the "
              "intensity_above_ceiling check, so the reading is treated as a likely sensor fault (verdict SUSPECT, rule score 0.93). All 4 neighbouring "
              "stations within 10 km were dry at that time (neighbour_isolated_wet), so nothing around it supports the value. Suggested reviewer label: "
              "confirmed_fault. A person decides; this explanation changes no verdict or score."),
    "SYN-B": ("Station SYN-B reported the same rain intensity of 2.0 mm/h for six readings in a row between 08:00 and 09:15 UTC on 2026-07-01. A real "
              "shower varies from reading to reading, so the frozen_intensity check flags it as a stuck sensor (verdict SUSPECT). The neighbours were dry "
              "during that time, which agrees with the sensor reporting rain that was not there. Suggested reviewer label: confirmed_fault. A person "
              "decides; this explanation changes no verdict or score."),
    "SYN-C": ("At 16:00 UTC on 2026-07-01 station SYN-C reported a rain intensity of 450 mm/h, well above the 300 mm/h physical ceiling of the "
              "intensity_above_ceiling check. A value like that is far outside what a gauge can measure, so it is treated as a likely sensor or data "
              "fault (verdict SUSPECT). Suggested reviewer label: confirmed_fault. A person decides; this explanation changes no verdict or score."),
    "SYN-D": ("At 07:00 UTC on 2026-07-01 station SYN-D reported 6.0 mm/h of rain while all 4 neighbouring stations within 10 km were dry. The "
              "neighbour_isolated_wet check marks this UNCERTAIN (rule score 0.3): an isolated shower is possible, so magnitude or isolation alone is not "
              "called a fault. It is worth a reviewer's look, for example against a nearby radar or another gauge. Suggested reviewer label: "
              "needs_followup. A person decides; this explanation changes no verdict or score."),
    "SYN-E": ("At 17:00 UTC on 2026-07-01 station SYN-E reported a rain intensity of -2.5 mm/h. Rain intensity cannot be negative, so the "
              "negative_value check marks the reading as a fault (verdict SUSPECT). A negative value usually points to a sensor offset or a data error. "
              "Suggested reviewer label: confirmed_fault. A person decides; this explanation changes no verdict or score."),
}


def demo_answer(station_id: str) -> Optional[str]:
    return ANSWERS.get((station_id or "").strip().upper())
