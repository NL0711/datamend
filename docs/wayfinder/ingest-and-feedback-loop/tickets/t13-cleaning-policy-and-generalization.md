---
title: How is cleaning configured so it stays correct for rainfall and for other weather parameters?
labels: [wayfinder:grilling]
status: open
assignee:
parent: MAP
blocked_by: []
---

## Question

The Explore step auto-cleans imported data (interpolation and exclusion, each with a reason). Cleaning that is right for one variable is wrong for another, so it must be configurable and driven by what the dataset actually is, and the design must generalise beyond rainfall.

## Owner requirement (2026-11-20, verbatim intent)

- If a dataset does not contain zero (dry) values, interpolation must not run: for example the CWC rainfall files list only non-zero hours, so a missing hour may be a dry hour and interpolating would invent rain.
- In that case the user can ask the AI agent for the best cleaning approach for their data.
- The cleaning step is configurable (the user can switch interpolation off, or choose other steps).
- This matters for rainfall but also for generalisation to other weather parameters. Generalisation is important.

## Proposed design (to be confirmed, then built by the Explore and frontend work)

1. **A variable profile per dataset**, detected from the data and editable by the user, never guessed silently: parameter name; kind (`intermittent_accumulation`, for example rainfall, or `continuous_state`, for example temperature, pressure, humidity); `reports_zero_values` (detected: if the smallest value is above zero, or no zeros exist, the dataset omits zeros); cadence (median interval and how regular it is); units; valid range; missing-value codes.
2. **A cleaning policy** is an ordered list of steps, each with parameters, stored with the run (reproducible): remove duplicates, normalise units, exclude impossible values (range from the profile), fill gaps (`none`, `linear`, `previous`), cap on gap length. Defaults come from the profile:
   - continuous state: linear fill allowed for gaps up to a few steps;
   - intermittent accumulation that reports zeros: no filling by default (a missing value stays missing and is flagged); linear fill only if the user turns it on, labelled imputed;
   - intermittent accumulation that omits zeros: gap filling is switched off and cannot be turned on without an explicit, recorded override.
   "Allowed" does not mean "recommended": even where zeros are reported, rain is not smooth, so for rainfall the default is to leave gaps missing.
3. **The assistant answers "what is the best cleaning for my data?"** from the profile and real counts (share of zeros, gap lengths, cadence) and names the rule it applied. The baseline is rule-based and always works; the AI narrator may add wording when connected. It only advises: it never changes data, and imputed values are always labelled (`basis: derived`).
4. **Generalisation boundary:** import, explore, profiling, cleaning and the map are parameter-agnostic. Validation verdicts and evidence stay rainfall-only until checks for another parameter exist and are evaluated. A non-rainfall dataset is therefore cleaned and explored but is NOT given verdicts, and the platform says so.

## Decided (owner, 2026-11-20)

The owner approved the amendment of `AGENTS.md` sections 1, 6 and 7: "a complete weather variable-profile also suited for rainfall and cleaning layer for other parameters; verdicts only where checks exist". `AGENTS.md` was edited accordingly. The generic layer is new, parameter-agnostic code and does not extend the legacy temperature, pressure and humidity code.

## Still needs the owner

1. Which other parameters first (temperature, humidity, pressure, wind), and a sample file of each to profile (the profile detection is tested on generated data only).
2. The default maximum gap for continuous variables (the build starts with a small number of steps; confirm or change).
3. Whether the old temperature, pressure and humidity code should still be removed as planned now that a generic layer exists.
