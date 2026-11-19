---
title: How do AI proposals, reviewer decisions, corrections and labels relate?
labels: [wayfinder:grilling]
status: closed
assignee: built on feature/ingest-pipeline (2026-11-20)
parent: MAP
blocked_by: [t01-storage-schema]
---

## Question

Define the data model and rules for the reviewer loop: what an AI proposal contains and where it is stored (separately, marked generated); what an accepted correction is (the original value is kept, the corrected one stored beside it with who, when and why); how a reviewer decision becomes a label with its tier (real reviewer, synthetic, simulated, never pooled); the random audit sample of unflagged data and its weighting so the model does not only learn to agree with itself; how "needs follow-up" and "unsure" are treated; and what the review screen must show for model-derived flags.

## Resolution (2026-11-20, decided by building on `feature/ingest-pipeline`)

**Decided and built** (`backend/app/pipeline/proposals.py`, `audit.py`, `snapshot.py`, `models.py`, `backend/app/api/pipeline.py`; tests in `tests/test_pipeline.py`):

- **Proposals are generated and apart from the data.** `pipeline_proposals` holds run, row, station, kind (`exclude_value`, `review_peak`, `review_repeat`), original and proposed value, text, generator (`baseline-rules`), `generated = true` and a status (`pending`, `accepted`, `rejected`) with who and when. `proposal_dict` always returns the label "generated, not a decision". Generating again never duplicates a proposal (same row and kind). Proposers sit behind a `Proposer` protocol (`PROPOSERS` registry); the baseline is plain rules, with no model.
- **What the baseline proposes:** an impossible daily total, so treat it as no data (`exclude_value`, proposed value empty); an hourly peak above `checks.INTENSITY_CEILING` (`review_peak`); a repeated positive total (`review_repeat`). The two review kinds suggest no value.
- **A correction keeps the original beside it.** Accepting `exclude_value` (or accepting with a `corrected_mm`) writes a `pipeline_corrections` row: original value, corrected value (empty means excluded), proposal id, reviewer, note, time. Observations are never touched; `effective_mm` and the snapshot's `mm_effective` apply corrections on read.
- **A decision becomes a label through the existing review table.** Accepting a proposal on a flagged row also writes a `Review` (decision `confirmed_fault`, reviewer, the proposal id in the note) in the validation platform's own table, so the review queue, exports and summary see it. Rejecting a proposal only closes it; the reviewer records a false alarm or genuine extreme through the existing review screen. Reviewer decisions map to labels in `snapshot.LABEL_OF`: `confirmed_fault` to fault, `false_alarm` to clean, `genuine_extreme` to genuine extreme. `needs_followup` is not a label, and a later follow-up on a row removes its earlier label from the snapshot.
- **Label tier:** every snapshot row carries `label_tier = "real_reviewer"`. No synthetic or simulated rows enter this path, so there is nothing to pool; the UK replay stays separate.
- **Audit sample:** `audit.draw` samples at random, without replacement, from rows of the run whose verdict is OK and that are not already drawn (at most 500 per call, optional seed for reproducibility). All drawn items share one inclusion probability (drawn so far divided by all OK rows) and weight 1 divided by that, recomputed over old and new items at every draw, so a second draw is not mis-weighted. Decisions are `ok`, `missed_fault` or `unsure`; `unsure` is never a label. `audit.estimate` gives the weighted missed-fault rate with a Wilson 95% interval, labelled an estimate for that run by one reviewer, not ground truth. In a snapshot, audit rows carry their weight and `random_sample = true`; reviewed flagged rows carry weight 1 and `random_sample = false`.
- **Unreviewed rows are never clean.** Only decided rows enter a snapshot.

**Not taken:** auto-accepting any proposal; treating "unsure" or "needs follow-up" as a label; pooling label tiers.

**Caveats and not built:**

- **One reviewer.** The reviewer is a free-text name (at most 60 characters) behind the shared admin token; there are no accounts, roles, per-reviewer agreement or second opinion. Every label is one person's judgement.
- **The LLM proposer is NOT IMPLEMENTED** (the narrator team's service); it would be a second `Proposer`. Asking for it returns an error that says so.
- **The review screen for model-derived flags is not built**, because no model-derived flag exists yet (no scoring on the server). Today's flags are rule-based and use the existing evidence view.
- **Proposals are only for the three baseline cases.** A flagged day that is, for example, only an isolated-wet neighbour hit gets no proposal; the reviewer still labels it through the review screen.
- **Audit sampling covers verdict-OK rows only**, so a genuine extreme or fault the checks called UNCERTAIN is not in the random sample; those are reviewed by choice and are not a random sample either. The missed-fault estimate is therefore about OK days only.
- **The audit interval is a Wilson interval on a weighted proportion** whose weights are all equal in one run; it is not corrected for the finite pool.
- **Assumed, not measured:** nothing here was run with a real reviewer's labels; the tests use generated CWC-shaped files.

**Closed because** the data model and rules asked for are decided and built. What was deferred (several reviewers, the LLM proposer, model-derived flag display) is under "Not yet specified" in the MAP.
