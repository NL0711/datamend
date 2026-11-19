---
title: What does the dashboard look like for a validation platform?
labels: [wayfinder:prototype]
status: closed
assignee: NL0711 (claimed 2026-11-19, closed 2026-11-19)
parent: MAP
blocked_by: []   # t05 closed 2026-11-19
---

## Question

Make a cheap rough prototype to react to (an outline or a stub screen set, not production code): upload and runs list, run report, series viewer with flagged readings and reasons, live gauge feed, and an evidence/explanation panel that clearly shows the narrator as a plug-in (NOT IMPLEMENTED until the teammate delivers). Decide which views exist, what is dropped from the current dashboard (overview, sensor health, injector, T/P/RH tabs), and the navigation.

## Prototype built (2026-11-19), verdict pending

Three structurally different variants, mounted as an extra tab ("Validation (PROTOTYPE)") of the existing app, switchable with `?variant=A|B|C`, the floating bar or the arrow keys. Read-only, in memory, SYNTHETIC sample data (five stations, 480 readings, faults hand-placed to show every verdict and check; headline numbers computed from the rows). No backend. Code is in `frontend/src/prototype-validation/` plus five lines in `frontend/src/App.tsx`; run `npm --prefix frontend run dev` and open `http://localhost:5199/?variant=A`.

- **A, report first:** a document-style run report (headline measured numbers, checks that fired, checks not run, export buttons, PDF marked not implemented); flagged rows expand inline into evidence; a second tab for the live gauge feed; a runs list with the demo-storage label.
- **B, timeline first:** station chips, one large series chart with verdict markers, a swimlane per check, and a sticky inspector with the evidence on the right.
- **C, triage queue:** a live strip on top, a filterable worklist of flagged readings (highest rule score first) on the left, and a decision pane with the evidence on the right.

- **D, timeline over queue (added after the owner's reaction):** the owner first picked A, then redirected to "B timeline first, keep the graph the entire width, and below it add the C data". D is exactly that: B's series chart and check lanes at full width on top, C's live strip, filterable worklist and decision pane below, linked (clicking a chart marker, a lane tick or a queue item selects the same reading). `?variant=D` is the default.

All three show: the original row untouched, the evidence with measured/assumed/derived tags, the baseline explanation marked generated, and the narrator slot marked NOT IMPLEMENTED. Open question for the owner: which variant, or which parts of each (for example B's chart with C's queue), and which current views are dropped.

## Resolution (2026-11-19, confirmed by the owner)

Settled with the owner. The owner first picked A, then redirected to B over C; variant D is that layout.

1. **Chosen layout: D, timeline over queue.** B's series chart (intensity bars, accumulation line, verdict markers) and its check lanes at the full width of the page; below them C's live strip, a filterable worklist of flagged readings (highest rule score first) and a decision pane with the evidence. The three are linked: a chart marker, a lane tick or a queue item selects the same reading. A's report-first layout and C's full-page queue are not used.
2. **Views and navigation (four rail items).** Runs (the list, plus "new run" upload); Run view (variant D, including the headline measured numbers, the checks-not-run list and the JSON/CSV export buttons; PDF stays NOT IMPLEMENTED); Live gauge feed; Settings trimmed to what the platform needs (feed city and interval, accumulation mode, narrator URL). Dropped from the current rail: Command Center, Live Telemetry, Alert Center, Sensor Health, Event Forensics, Data Explorer, Anomaly Lab, XAI Reasoner and Locations.
3. **The worklist at real size.** Server-side pagination at 50 flagged rows per page, sorted by rule score, filtered by verdict, check or station; the evidence of a row is loaded only when it opens (one GET, within the 64 KB evidence cap). The chart shows one station at a time and must downsample a long series server-side.
4. **Always on screen:** the original row untouched; evidence with measured, assumed or derived tags; the baseline explanation marked generated; the narrator slot marked NOT IMPLEMENTED until delivered; the "demo storage, resets on restart" label on the runs list; synthetic data labelled as synthetic.
5. **Capture of the prototype.** The four variants stay as a primary source on a throwaway branch (not on `main`); only the validated layout is rebuilt properly in a build slice. The prototype files are `frontend/src/prototype-validation/` plus five lines in `frontend/src/App.tsx`.
