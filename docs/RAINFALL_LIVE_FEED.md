# Live rain-gauge feed (Weather Union)

Status 2026-11-19: built and tested; verified against the real API for 9 Mumbai stations (all dry at the time, so no rain
reading has been seen yet). Code: `backend/app/rainfall/`, endpoints under `/api/rainfall`, tests `tests/test_rainfall_feed.py`
(27 pass, mocked transport). NOT built: a dashboard view, persistence of readings to the database, any trained-model scoring.

## Source
Weather Union by Zomato, free key, 1000 calls per day (reset after 12 AM). About 580 stations in 30 cities (313 automated weather
systems, 267 rain gauges), catalogue in `backend/app/rainfall/data/weather_union_stations.csv` (built by
`scripts/build_weather_union_catalog.py` from Zomato's published list). Header `x-zomato-api-key`; endpoint
`GET /get_locality_weather_data?locality_id=...` returns `rain_intensity` and `rain_accumulation` (rain-gauge stations return only those).

## What the provider does NOT document (never assumed silently)
* units of `rain_intensity` and `rain_accumulation` (assumed mm and mm/h),
* the period of `rain_accumulation` (running total since a reset, or amount since the last reading),
* the observation time (no timestamp in the response; times are when we received the reading).
Every reading is appended to a raw log (`WEATHER_UNION_RAW_LOG_PATH`). The first time it rains, read that log for a station and
settle the accumulation mode (`WEATHER_UNION_ACCUMULATION_MODE`); every daily total carries `units_confirmed: false` until then.
Asking the provider (info@weatherunion.com) is the other route.

## Call budget
Polling N stations every T seconds costs 86400 N / T calls per day. The service raises T automatically so this stays under
`WEATHER_UNION_DAILY_CALL_BUDGET` (default 900), and the client refuses to send a call once the day's budget is used
(counted per IST calendar day). 9 stations every 15 minutes = 864 calls.

## Daily total
Rain day 03 UTC to 03 UTC (08:30 to 08:30 IST), the same definition as the IMD/RF25 daily grids. `cumulative` mode sums increases
and treats a drop as a counter reset; `per_reading` sums the readings. A day is `complete` only if readings cover it without a gap
over 60 minutes.

## Quality score (rules plus neighbour check, NOT a trained model)
Checks and fixed weights (design choices, not calibrated; there are no labels): negative value 0.95, intensity above 300 (assumed
mm/h) 0.9, counter jump above 50 mm in one reading 0.7, identical non-zero intensity for 6 readings 0.6, intensity above zero with a
flat counter 0.5, isolated wet or dry against at least 3 neighbours within 10 km (75 percent agreement) 0.3, counter reset 0.1.
Score = 1 - product(1 - weight). Assessment: `NO_DATA`, `SUSPECT` (a rule fired), `UNCERTAIN` (only the neighbour check disagrees:
convective rain can be genuinely local, so it is not called a fault), `OK`.

## Run it
Set `WEATHER_UNION_API_KEY` and `WEATHER_UNION_CITY` (see `.env.example`), start the backend, open `/api/rainfall/stations`.
With either unset the endpoints return 503 and nothing is polled. Needs `pydantic-settings` installed to read `.env`.

## Licence
Check Weather Union's terms (https://www.weatherunion.com/tnc/) before showing its data publicly; free access is stated for
"public good" with possible charges for very high-volume enterprise use.
