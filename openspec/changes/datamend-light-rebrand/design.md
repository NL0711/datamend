## Context

The dashboard is dark-only via two mechanisms: a centralized `datamend` Tailwind palette plus `--sg-*` CSS variables (`tailwind.config.js`, `index.css`), and hundreds of hardcoded dark hexes (`#152033`, `#1B2A44`, `#263B5E`, `slate-300/400` text) inside views. Icons come from lucide-react and appear in nav tabs, table rows, dossier sections, status strips, and action buttons. The product name "DataMend (AI)" appears in 40+ files: UI strings, `index.html` title, `frontend/package.json`, backend API metadata (`main.py` title, `config.py` PROJECT_NAME), README, run.bat, compose labels, docs, and code docstrings/logs.

## Goals / Non-Goals

**Goals:**

- One clean light theme across every view, with severity/status colors still instantly readable on light surfaces.
- Icons only in the tab navigation bar; everywhere else typography + color carry meaning.
- Consistent DataMend naming everywhere a human reads it; identifiers and compat-sensitive strings explicitly bounded.

**Non-Goals:**

- Dark-mode toggle or multi-theme support (single light theme).
- API route/schema renames, DB changes, ML changes.
- Renaming Python module paths, MQTT topics, or storage filenames.

## Decisions

- **Flip tokens, then sweep hardcoded hexes.** Change the `datamend` palette values and `--sg-*` variables to the light scale first (page `#F6F8FB`, surfaces white/`#EDF1F7`, borders `#D7DEE8`, text slate-900/600), keeping token *names* so class references keep working. Then convert remaining hardcoded dark hexes component by component to tokens or light values. Rationale: token flip fixes ~60% of surfaces in one edit; the sweep catches the rest. Alternative (rename token family to `datamend.*`) rejected: same visual result with diffs in every file.
- **Severity palette tuned for light backgrounds.** Keep hues (emerald/amber/rose/sky), deepen them one step (e.g. rose-600 on tinted rose-50 chips instead of rose-300 on navy) to hold ≥ 4.5:1 contrast for text. Charts (recharts) get light gridlines/tooltips via the shared chart props.
- **Navbar keeps icons; content drops them.** `App.tsx` tab items keep their lucide icons. All other views lose decorative icons (section headers, table cells, status strips, dossier); `StatusBadge` keeps color + label, no glyph. Triage action buttons become text-only. Rationale: icons-as-decoration add visual noise in dense ops views; nav icons aid fast tab scanning, so they stay.
- **Rebrand rule: humans read DataMend; machines keep working.** Display strings → "DataMend" (title case in prose/titles, `datamend` for package/ids/URLs); code identifiers, `backend.*` imports, `skyguard.db`, MQTT `datamend/#` topics, and API paths stay byte-identical. Rationale: renaming wire/storage/import identifiers breaks compat and existing deployments for zero user-visible gain; the spec's "everywhere" means everywhere a human reads.
- **Verification is `tsc` + `vite build` + rg sweeps.** No visual-snapshot infra exists; a production build plus targeted `rg` checks (no `DataMend` display strings left, no `from 'lucide-react'` outside nav + triage-exempt list) are the gates, plus manual smoke of each tab.

## Risks / Trade-offs

- [Risk] Missed dark hex in a rarely-opened panel (settings drawer, injector) → Mitigation: rg sweep for the known dark hex set (`#0F1726 #152033 #1B2A44 #233656 #0C1320 #263B5E`) must return only intentionally-kept hits (e.g. code-span styling).
- [Risk] Contrast regressions on severity chips/charts → Mitigation: deepen-on-light rule + manual check of AlertCenter/EventDetail/Overview against the palette table in design review.
- [Risk] Rebrand misses user-facing strings in backend logs/errors → Mitigation: rg sweep for `DataMend|datamend|DATAMEND` with an explicit allowlist file for compat-kept identifiers (topics, db filename, module paths).
- [Trade-off] Single theme means former dark-mode users get no choice — accepted per scope; a toggle can be a later change.
