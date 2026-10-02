## 2026-08-24T05:17:49Z
<USER_REQUEST>
You are m1_explorer_1.
Working Directory: c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard\.agents\m1_explorer_1
Workspace Root: c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard

Milestone: M1 — Simulator & Anomaly Injector Engine (Phases 1–4 of TODO.md)
Reference Inputs:
- Project Specification: c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard\PROJECT.md
- User Requirements: c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard\ORIGINAL_REQUEST.md
- Constraints: c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard\AGENTS.md
- Architecture: c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard\ARCHITECTURE.md
- TODO Plan: c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard\TODO.md
- Algorithmic Specs: c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard\.agents\survey_spec_miner_2\report.md

Your mission:
1. Read the specification files above, especially regarding diurnal generation and Magnus-Tetens thermodynamic modeling.
2. Design the complete architecture and implementation specifications for `backend/simulator/diurnal_generator.py`:
   - Sinusoidal temperature diurnal cycle $T(t)$ with configurable base, amplitude, solar peak (e.g. 14:00), daily noise.
   - Relative humidity $RH(t)$ inversely correlated with temperature under Magnus-Tetens saturation vapor pressure $e_s(T)$.
   - Pressure $P(t)$ with semi-diurnal atmospheric tides (12h) and synoptic Rossby pressure variations.
   - Support for configurable station metadata (station_id, lat, lon, elevation), time range (start_date, end_date, freq e.g. 5min), and DataFrame generation.
3. Write your analysis to c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard\.agents\m1_explorer_1\analysis.md and deliver a handoff.md.
4. Notify the orchestrator (conversation ID: 327adcb6-3df1-42e8-9da6-eaf0ceeb99da) via send_message.
</USER_REQUEST>
