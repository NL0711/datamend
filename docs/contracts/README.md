# Live rainfall evidence and explanations

Implemented on `rf`. The shared Word documents remain the full platform design; this contract describes the working live-feed adapter. Uploads, validation-run endpoints, per-run exports, the four-item dashboard and MCP hosting remain planned. The external narrator itself belongs to the AI team and is not shipped here.

## Explainable reasoning and decision making

The existing deterministic rainfall scorer owns the verdict. Evidence records its observed values, thresholds, fixed weights, relevant history and neighbour observations. Numbers carry `measured`, `assumed` or `derived` basis tags; the rule score is explicitly derived and uncalibrated. Checks that could not run have a reason. Generated text describes this recorded decision, not a hidden reasoning trace or a proven sensor diagnosis.

The template explainer works without AI. A narrator receives a serialized evidence copy and returns only text, contributions and a model ID. It has no API to edit observations, scores, verdicts or evidence. AI text can still be wrong: the interface labels it AI-generated and keeps the template and full evidence visible. No real-world accuracy or trained-model explanation is claimed.

## Live API

All paths below are under `/api/rainfall`. If `EVIDENCE_API_TOKEN` is set, include `Authorization: Bearer <token>`. The UI accepts this token in memory; it is not stored in browser storage. No external narrator token is sent to the browser.

| Method and path | Behaviour |
| --- | --- |
| `GET /evidence-schema` | Runtime schema, identical to `evidence-v1.schema.json`. |
| `GET /stations/{id}/evidence` | Current read-only decision evidence and SHA-256 `evidence_hash`; no narrator call or database write. |
| `POST /stations/{id}/explanations` | Body: `{"evidence_hash":"<hash from GET>","use_narrator":false}`. Store a template explanation and immutable evidence snapshot; optionally request AI text. Returns 201. |
| `GET /explanations/{id}` | Retrieve the original saved evidence, template and optional narrator reply, even after live readings change. |

The live contract bundles one row's per-check evidence under `evidence.checks`; the row verdict and score appear at the top and on each fired check. It is an adapter for the design's future per-run evidence endpoints, not an implementation of those endpoints. `evidence-v1.example.json` contains explicitly synthetic readings.

No reading yet gives 409; unknown station gives 404; feed disabled gives 503. A changed evidence hash gives 409: reload before explaining. Oversize evidence gives 413 rather than silently dropping decision facts. There is no evidence write route.

## Narrator setup

Set these only in local/deployment environment variables:

```dotenv
NARRATOR_URL=https://your-narrator.example/explain
NARRATOR_TOKEN=your-private-outbound-token
EVIDENCE_API_TOKEN=your-private-evidence-api-token
```

With no narrator URL, the template remains available and AI requests say “AI narrator not connected”. The Rainfall reasoning tab works when the Weather Union feed is configured; it shows the real disabled/empty state otherwise.

Outbound POST shape:

```json
{"schema_version":"evidence-v1","run_id":"live:<ending-date>","row_ref":"<station>:<received-time>","evidence":{"checks":[],"...":"full decision evidence"}}
```

Response shape (the contribution factor must name a check in the supplied evidence):

```json
{"text":"Explanation from the evidence","contributions":[{"factor":"ACCUMULATION_JUMP","note":"Evidence-backed contribution"}],"model_id":"team-model-version","generated":true,"confidence":null}
```

The adapter rejects extra fields (including verdict/score overrides), unknown contribution factors, non-null confidence, malformed or empty text, non-success responses and redirects. Request/response limits are 64 KB; the total timeout is 20 seconds. Any failure falls back to the template without exposing remote error bodies. One outbound narrator request per station per minute is allowed per backend process. These limits are design choices; multiple workers require a shared limiter.

The `explanations` SQLAlchemy table is append-only through these routes, with evidence hash, JSON snapshot, template, narrator reply/status and creation time. It uses the existing database and has no dependency on future validation-run tables. Demo SQLite can reset on hosting restarts; no durability guarantee or full 50-run retention policy is claimed yet.

## Validation

```bash
python -m pytest tests/test_deployment_config.py tests/test_rainfall_feed.py tests/test_rainfall_explanations.py -q
cd frontend
npm ci
npm run build
```

Tests use generated readings, a temporary SQLite database and mocked HTTP. They cover uncertainty, assumptions, schema conformance, immutable saved evidence, stale readings, auth, response validation, narrator failures and baseline fallback. The live AI team's service has not been connected or tested. For deployment, set the evidence token and HTTPS narrator endpoint. Never bake private narrator credentials into `VITE_*` variables.
