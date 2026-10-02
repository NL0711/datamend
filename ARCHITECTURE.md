# SKYGUARD AI — SYSTEM ARCHITECTURE

## 1. SYSTEM OBJECTIVE

SkyGuard AI is an intelligent AWS data quality and sensor health platform.

It receives Temperature, Atmospheric Pressure and Relative Humidity observations and determines whether observations are:

- normal
- anomalous
- probable sensor fault
- probable genuine meteorological event
- uncertain

The system then produces:

- anomaly score
- confidence
- severity
- root-cause/fault classification
- explanation
- sensor health
- optional degradation prediction
- optional corrected estimate

---

# 2. HIGH-LEVEL ARCHITECTURE

```text
                    AWS DATA SOURCE
                          |
                          v
                +-------------------+
                | INGESTION LAYER   |
                +---------+---------+
                          |
                          v
                +-------------------+
                | VALIDATION        |
                +---------+---------+
                          |
                          v
                +-------------------+
                | PREPROCESSING     |
                +---------+---------+
                          |
                          v
                +-------------------+
                | FEATURE ENGINE    |
                +---------+---------+
                          |
             +------------+-------------+
             |            |             |
             v            v             v
        RULE ENGINE   TEMPORAL ML   MULTIVARIATE ML
             |            |             |
             +------------+-------------+
                          |
                          v
                +-------------------+
                | ANOMALY FUSION    |
                +---------+---------+
                          |
                          v
                +-------------------+
                | FAULT CLASSIFIER  |
                +---------+---------+
                          |
             +------------+-------------+
             |            |             |
             v            v             v
        CONFIDENCE    EXPLANATION   HEALTH ENGINE
             |            |             |
             +------------+-------------+
                          |
                          v
                +-------------------+
                | ALERT ENGINE      |
                +---------+---------+
                          |
                          v
                +-------------------+
                | DATABASE          |
                +---------+---------+
                          |
                          v
                +-------------------+
                | FASTAPI           |
                +---------+---------+
                          |
                          v
                +-------------------+
                | WEB DASHBOARD     |
                +-------------------+
```

---

# 3. DATA FLOW

## Historical Mode

```text
CSV / JSON / Parquet
        ↓
Schema Validation
        ↓
Cleaning
        ↓
Feature Engineering
        ↓
Anomaly Detection
        ↓
Fault Classification
        ↓
Confidence
        ↓
Health
        ↓
Database
        ↓
Dashboard
```

## Real-Time Mode

```text
Sensor Observation
        ↓
API / Stream
        ↓
Validation
        ↓
Feature Buffer
        ↓
Inference
        ↓
Alert
        ↓
Database
        ↓
WebSocket/API
        ↓
Dashboard
```

---

# 4. DATA SCHEMA

Required:

- timestamp
- temperature
- pressure
- humidity

Optional:

- station_id
- latitude
- longitude
- elevation

Observation record:

```json
{
  "timestamp": "2026-08-24T12:30:00Z",
  "station_id": "AWS_001",
  "temperature": 28.4,
  "pressure": 1008.7,
  "humidity": 72.1
}
```

---

# 5. DATABASE

SQLite initial implementation.

### stations

| Column | Type |
|--------|------|
| id | INTEGER PRIMARY KEY |
| station_id | TEXT UNIQUE |
| name | TEXT |
| latitude | REAL |
| longitude | REAL |
| elevation | REAL |
| status | TEXT |
| created_at | DATETIME |

### observations

| Column | Type |
|--------|------|
| id | INTEGER PRIMARY KEY |
| station_id | TEXT |
| timestamp | DATETIME |
| temperature | REAL |
| pressure | REAL |
| humidity | REAL |
| validation_status | TEXT |
| created_at | DATETIME |

### anomaly_events

| Column | Type |
|--------|------|
| id | INTEGER PRIMARY KEY |
| observation_id | INTEGER |
| anomaly_score | REAL |
| confidence | REAL |
| severity | TEXT |
| anomaly_type | TEXT |
| classification | TEXT |
| explanation | TEXT |
| created_at | DATETIME |

### sensor_health

| Column | Type |
|--------|------|
| id | INTEGER PRIMARY KEY |
| station_id | TEXT |
| timestamp | DATETIME |
| health_score | REAL |
| health_status | TEXT |
| anomaly_rate | REAL |
| drift_score | REAL |
| data_quality_score | REAL |

### model_runs

| Column | Type |
|--------|------|
| id | INTEGER PRIMARY KEY |
| model_name | TEXT |
| version | TEXT |
| dataset_version | TEXT |
| metrics | TEXT (JSON) |
| created_at | DATETIME |

---

# 6. ML PIPELINE

## Stage 1: Baseline

Implement a strong deterministic baseline first.

Components:

- range validation
- rate-of-change
- missing-value detection
- duplicate detection
- persistence/frozen-value detection
- rolling statistics

This establishes the baseline against which ML is compared.

---

# 7. TEMPORAL MODEL

Candidate:

GRU/LSTM Autoencoder

Input:

historical sequences of:
- temperature
- pressure
- humidity

Example:

t-9, t-8, t-7, ..., t-1, t

Model learns normal temporal patterns.

Output:

reconstruction error

Convert reconstruction error into anomaly score.

Start with a simpler model if dataset size does not justify LSTM/GRU.

---

# 8. NON-TEMPORAL ML BASELINE

Candidate:

Isolation Forest

Purpose:

Provide an interpretable baseline for multivariate anomaly detection.

Input features may include:

- temperature
- pressure
- humidity
- rolling mean
- rolling std
- rate of change

---

# 9. MULTIVARIATE CONSISTENCY

Create engineered relationships/features.

Examples:

- temperature rate of change
- pressure rate of change
- humidity rate of change
- rolling statistics
- normalized deviations
- cross-variable relationships

Do not hardcode scientifically unsupported formulas.

Validate feature usefulness experimentally.

---

# 10. ANOMALY FUSION

Example architecture:

```text
Rule Score
     |
Temporal Score
     |
Isolation Forest Score
     |
Multivariate Score
     |
     v
+---------------------+
| Anomaly Fusion      |
+----------+----------+
           |
           v
 anomaly_score
 confidence
 severity
```

The exact fusion formula must be determined experimentally.

Do not simply average all scores without validation.

---

# 11. CLASSIFICATION

Output:

- NORMAL
- SPIKE
- DROPOUT
- FROZEN
- DRIFT
- MULTIVARIATE_INCONSISTENCY
- DATA_CORRUPTION
- UNCERTAIN_EVENT

The classifier may combine:

- rule evidence
- ML features
- temporal evidence
- anomaly score

---

# 12. CONFIDENCE

Confidence must reflect model evidence.

Do not confuse:

anomaly_score

with:

confidence

They represent different concepts.

Example:

anomaly_score = 0.92
confidence = 0.87

means:

"The observation appears highly anomalous, and the system has fairly high confidence in that assessment."

---

# 13. SEVERITY

Suggested:

- LOW
- MEDIUM
- HIGH
- CRITICAL

Severity should be determined using validated logic.

---

# 14. EXPLAINABILITY

Each alert should expose evidence.

Example:

```text
Temperature contribution: HIGH
Pressure contribution: MEDIUM
Humidity contribution: HIGH
Temporal deviation: HIGH
Persistence: LOW
```

If SHAP is used:

- use the actual trained model
- save model/version metadata
- generate explanations from actual inference

---

# 15. SENSOR HEALTH ENGINE

Concept:

```text
                    Sensor Health
                         |
        +----------------+----------------+
        |                |                |
        v                v                v
   Anomaly Rate      Data Quality       Drift
        |                |                |
        +----------------+----------------+
                         |
                         v
                  Health Score
                    0–100
```

The exact formula should be configurable and documented.

---

# 16. DEGRADATION ENGINE

Advanced phase.

Potential features:

- anomaly frequency trend
- drift trend
- missing data trend
- confidence-weighted fault rate
- health score trend

Output:

- stable
- degrading
- high_risk
- maintenance_recommended

Do not claim remaining useful life unless the dataset supports it.

---

# 17. CORRECTION ENGINE

Optional.

```text
Anomalous Observation
        ↓
Context Window
        ↓
Prediction Model
        ↓
Estimated Value
        ↓
Confidence
```

Raw observation must always remain unchanged.

---

# 18. BACKEND ARCHITECTURE

```text
backend/
├── app/
│   ├── main.py
│   ├── api/
│   ├── services/
│   ├── models/
│   ├── schemas/
│   ├── db/
│   └── core/
│
├── ml/
│   ├── preprocessing/
│   ├── features/
│   ├── baselines/
│   ├── temporal/
│   ├── fusion/
│   ├── classification/
│   ├── explainability/
│   └── health/
│
├── data/
├── models/
├── tests/
└── scripts/
```

---

# 19. FRONTEND ARCHITECTURE

```text
frontend/
├── src/
│   ├── components/
│   ├── pages/
│   ├── charts/
│   ├── api/
│   ├── hooks/
│   ├── types/
│   └── utils/
```

Pages:

- Dashboard
- Live Monitoring
- Alerts
- Sensor Health
- Event Details
- Data Explorer
- Model Performance
- Settings

---

# 20. API DESIGN

Example:

```text
POST /api/data/upload
POST /api/observations
GET  /api/stations
GET  /api/stations/{id}
GET  /api/observations
GET  /api/anomalies
GET  /api/anomalies/{id}
GET  /api/health/{station_id}
GET  /api/metrics
POST /api/inference
```

Optional real-time:

```text
WebSocket /ws/live
```

---

# 21. MODEL ARTIFACTS

Store:

```text
models/
├── isolation_forest/
├── temporal_autoencoder/
├── classifier/
└── metadata/
```

Each model should have:

- version
- training data identifier
- feature schema
- training timestamp
- metrics
- configuration

---

# 22. DEPLOYMENT

### Initial

```text
Frontend
    ↓
FastAPI
    ↓
ML inference
    ↓
SQLite
```

### Future

```text
Frontend
    ↓
API Gateway
    ↓
FastAPI services
    ↓
PostgreSQL
    ↓
Model service
    ↓
Streaming infrastructure
```

---

# 23. EDGE AI

Edge deployment is an optional advanced phase.

Potential target:

ESP32 or low-power edge computer.

Do not force deep neural networks onto ESP32 without measuring feasibility.

Potential strategy:

```text
Edge:
basic validation
+
lightweight anomaly model

Cloud/server:
advanced model
+
explainability
+
degradation analysis
```

---

# 24. DESIGN PRINCIPLE

The architecture must remain modular.

Each component should be replaceable.

For example:

Isolation Forest

can later be replaced by:

XGBoost / Autoencoder / other model

without rewriting the entire backend.
