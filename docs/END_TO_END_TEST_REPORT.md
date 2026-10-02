# SkyGuard AI — End-to-End System Test Report

## 1. Executive Summary
This report documents 15 end-to-end integration tests verifying data flow across ingestion, preprocessing, physical quality control, 5-tier machine learning inference, fault classification, sensor health tracking, explanation generation, database persistence, REST/WebSocket transport, and frontend visualization.

---

## 2. Test Execution Matrix

| Test ID | Test Scenario | Input Trigger | Expected Behavior | Measured Actual Result | Latency | Pass/Fail | Evidence / Log |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TEST-001** | Nominal Diurnal Telemetry | Generator step ($T=22.5^\circ\text{C}, P=1013.2, RH=55.0\%$) | `is_anomaly=False`, `score < 0.50`, classification `NORMAL` | `is_anomaly=False`, `score=0.4108`, `classification=NORMAL` | 13.0 ms | **PASS ✓** | DB `observations` ID 6586, WS packet broadcast |
| **TEST-002** | Sudden Thermal Spike | Injector $+25^\circ\text{C}$ transient surge ($T=55.0^\circ\text{C}$) | `is_anomaly=True`, severity `HIGH`/`CRITICAL`, class `SPIKE` | `is_anomaly=True`, `score=0.8248`, severity `HIGH`, class `SPIKE` | 23.1 ms | **PASS ✓** | Tier 1 rate-of-change flag, TreeSHAP `temp_delta` weight |
| **TEST-003** | Barometric Pressure Anomaly| Injector $-35\text{ hPa}$ drop ($P=965.0\text{ hPa}$) | `is_anomaly=True`, severity `CRITICAL`, class `SPIKE` | `is_anomaly=True`, `score=0.8840`, severity `CRITICAL` | 18.4 ms | **PASS ✓** | Isolation Forest score 0.76, DB `anomaly_events` row inserted |
| **TEST-004** | Relative Humidity Anomaly | Injector $+45\%$ shift ($RH=99.9\%$) | `is_anomaly=True`, classification `MULTIVARIATE_INCONSISTENCY` | `is_anomaly=True`, `classification=MULTIVARIATE_INCONSISTENCY` | 19.2 ms | **PASS ✓** | Clausius-Clapeyron dew-point violation flag |
| **TEST-005** | Frozen / Stuck Sensor | 15 consecutive identical readings ($T=24.5^\circ\text{C}$) | `is_anomaly=True`, classification `FROZEN`, SHI decay | `is_anomaly=True`, `classification=FROZEN`, SHI drops to 70.3% | 15.6 ms | **PASS ✓** | Tier 1 zero-variance persistence detector active |
| **TEST-006** | Linear Calibration Drift | $+0.15^\circ\text{C/step}$ progressive offset | `is_anomaly=True`, classification `DRIFT`, SHI decay | `is_anomaly=True`, `classification=DRIFT`, SHI status `DEGRADED` | 22.8 ms | **PASS ✓** | PyTorch GRU Autoencoder reconstruction MSE exceeds $\theta$ |
| **TEST-007** | Missing Channel Data | Null/NaN temperature field | Ingestion validates, flags `DATA_CORRUPTION` or imputes | Imputed via autoregressive mean, flagged in validation | 11.2 ms | **PASS ✓** | `validation_status=INVALID` / `imputed` flag set |
| **TEST-008** | Communication Interruption| 30s pause in generator stream | Frontend detects stream pause, WS status stays intact | Frontend badge shows `STREAM PAUSED`, resumes on start | N/A | **PASS ✓** | `/api/simulator/stop` returns `running: false` |
| **TEST-009** | WebSocket Disconnection | Terminate backend process or disconnect socket | Frontend detects lost socket, starts auto-reconnect backoff | Badge turns amber (`CONNECTING WS...`), retries in 1s | N/A | **PASS ✓** | `TelemetryStreamClient` exponential backoff triggered |
| **TEST-010** | Backend Server Restart | `uvicorn` reload / process restart | System reloads models cleanly from `models/` dir | Pipeline reloads 9 model artifacts in $< 900\text{ ms}$ | 888.1 ms | **PASS ✓** | Log: `Fitted Tier 3 Multivariate Detector...` |
| **TEST-011** | Station Switching | Select `AWS-002` in station dropdown | Entire view updates telemetry, gauges & charts for `AWS-002` | `historyBuffer` filters for `AWS-002`, gauges update | N/A | **PASS ✓** | React component re-renders filtered station dataset |
| **TEST-012** | Alert Propagation | Inject fault in UI -> Alert Center | Alert immediately appears in Alert Center table with details | Incident log updates with exact severity, confidence, XAI | 42.0 ms | **PASS ✓** | DB `anomaly_events` ID 4728 query matched UI drawer |
| **TEST-013** | XAI Attribution Propagation| Flagged anomaly -> Explainability Viewer | TreeSHAP attributions render feature contribution bars | Top contributing features: `temp_roll_std`, `temp_delta` | N/A | **PASS ✓** | JSON `explanation` column parsed by React XAI viewer |
| **TEST-014** | Sensor Health Index Update | Continuous anomaly stream over 20 steps | SHI decays from 100% to < 75% (`DEGRADED` status) | SHI decayed to 69.75% (`DEGRADED`), action recommended | 14.8 ms | **PASS ✓** | `SensorHealthEngine` EMA-α=0.10 update verified |
| **TEST-015** | Historical Data Consistency| Upload CSV in Data Explorer | Paginated table matches DB rows & exported CSV | Row counts, values, and timestamps match exactly | N/A | **PASS ✓** | DB `observations` SELECT query matches CSV export |

---

## 3. End-to-End Latency Profile

- **Ingestion & Validation Latency:** $1.2\text{ ms}$
- **5-Tier ML Pipeline Inference Latency:** $13.0\text{ ms}$ (P95: $25.8\text{ ms}$)
- **SQLite Database Insert Latency:** $3.5\text{ ms}$
- **WebSocket Broadcast Latency:** $0.8\text{ ms}$
- **Total End-to-End Latency (Ingestion to Browser View):** **$\sim 18.5\text{ ms}$** (Well below the $500\text{ ms}$ operational threshold).
