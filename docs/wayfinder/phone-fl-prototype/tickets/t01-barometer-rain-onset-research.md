---
title: What does existing research say about predicting rain from phone barometer pressure tendency?
labels: [wayfinder:research]
status: closed
assignee: research agent (claimed 2026-11-19, closed 2026-11-19)
parent: MAP
blocked_by: []
---

## Question

Find primary sources on short-term rain-onset prediction from surface pressure tendency (WMO tendency definitions; smartphone-barometer studies, for example crowdsourced pressure networks; sensor noise, drift and altitude effects; what skill is realistic). Also what label sources exist for tap-style reports. Output: `docs/research/phone-barometer-rain-onset.md`. Feeds the ticket on the model, features and labels.

## Resolution (2026-11-19)

Findings are in `docs/research/phone-barometer-rain-onset.md` (summarising fetch tool, so not verbatim; unconfirmed items are marked UNVERIFIED or NOT FOUND there). A fact-finding result, not a decision.

- WMO pressure tendency is a 3-hour signed change plus a shape class (WMO-No. 8 Vol. I Ch. 3; code register 0-10-063). A 15-minute or 1-hour window is a DataMend choice and must be named differently.
- Phone barometers are good on relative change and poor on absolute level: two phones tested against a reference had stable biases of +0.96 and -2.06 hPa and correlation of 0.97 or higher with it (Hintz, Vedel and Kaas 2019); screening discarded 80 to 90 percent of crowd observations. 1 hPa is about 8 m of height, so changing floors looks like weather.
- **No primary source found reporting measured skill (hit rate, false-alarm rate, lead time) for predicting rain onset from one device's pressure tendency.** The prototype needs its own baseline and evaluation, and no skill can be assumed.
- No data on tap-label timing or error; mPING is a US precipitation-type source, not onset timing.
- Android 9 and later give background apps no sensor events (matches the on-device training research).
- Not checked: the target phone's actual sensor and its reporting mode.
