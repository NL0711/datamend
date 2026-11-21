---
title: Which 9 gauges does the live feed poll, given where the phones are?
labels: [wayfinder:grilling]
status: closed
assignee: NL0711 (claimed 2026-11-19, closed 2026-11-19)
parent: MAP
blocked_by: []
---

## Question

Phone labels come only from polled gauges within 10 km (assumed). `pick_cluster` in `backend/app/rainfall/service.py` currently chooses the 9 stations nearest the city's median point so they are each other's neighbours, and has no per-station setting. The owner's phones are at Goregaon, Malad, Bhandup and Dadar; Dadar West (10.6 km from the nearest polled gauge, Andheri East) is not polled, and a Vasai phone was considered and dropped. Decide the polled set.

## Resolution (2026-11-19, confirmed by the owner; the dropped gauge is the author's choice, open to change)

Distances from `backend/app/geo.py` on catalogue coordinates, not exact phone positions.

1. **Polled set (9, call budget unchanged).** Goregaon East, Goregaon West, Kandivali East, Andheri West, Malad West, Andheri East, Powai, Bhandup West (all already polled) plus **Dadar West** (new). **Mulund West is dropped** to stay at 9. Vasai is not added (the owner removed that phone).
2. **Phones (final, owner, 2026-11-19).** Bhandup, Goregaon and Dadar: 3 clients, each at a polled gauge (Bhandup West, Goregaon West or East, and the new Dadar West). Pairwise separation is roughly 10 km (Goregaon to Bhandup), 16 km (Goregaon to Dadar) and 18 km (Bhandup to Dadar), approximate from catalogue coordinates, so no two are a strongly correlated pair. Malad is no longer a phone location; Malad West stays polled as a neighbour for the cluster's neighbour check. Earlier intermediate answers (4 phones with Malad, 2 phones, a Vasai phone) are superseded.
3. **Cost.** Dadar West has no polled neighbour within 10 km, so the neighbour check is "not run" for it and its verdict, and so its label guard, rests on the rule checks alone; the evaluation rules and the app say so. The live feed and the alerts lose Mulund West's coverage.
4. **How.** A small code change in the build: an explicit list of station IDs replacing the automatic cluster choice (a setting with the current automatic choice as the default is the build slice's call). Nothing in the deployed settings was changed while mapping.
