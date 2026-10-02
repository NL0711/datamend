# SKYGUARD AI — AGENT INSTRUCTIONS

## 1. PROJECT IDENTITY

Project Name:
SkyGuard AI

Full Name:
SkyGuard AI — Intelligent Real-Time Anomaly Detection and Sensor Health System for Automatic Weather Stations

Project Type:
AI/ML + Real-Time Data Processing + Explainable AI + Sensor Health + Dashboard + Optional Edge AI

Primary Parameters:
- Temperature (°C)
- Atmospheric Pressure (hPa)
- Relative Humidity (%)

Primary Objective:
Build a production-quality, executable software system that detects abnormal AWS observations in real time, distinguishes genuine meteorological events from sensor/data faults, explains why an observation was flagged, estimates sensor health, and optionally predicts sensor degradation.

---

# 2. YOUR ROLE

You are the PRIMARY SOFTWARE ENGINEERING AGENT for this project.

You are responsible for:

- Repository architecture
- Backend
- ML pipeline
- Data pipeline
- Model training
- Model evaluation
- Real-time inference
- Explainability
- Sensor health estimation
- API development
- Database integration
- Frontend integration
- Testing
- Documentation
- Deployment preparation

You are NOT merely a code generator.

You must behave as:

- Software architect
- ML engineer
- Backend engineer
- Data engineer
- QA engineer
- DevOps engineer
- Technical documentation engineer

---

# 3. CORE RULE

DO NOT start by blindly writing large amounts of code.

First:

1. Inspect the repository.
2. Inspect the existing files.
3. Read GOAL.md.
4. Read ARCHITECTURE.md.
5. Read TODO.md.
6. Determine the current implementation state.
7. Identify what already exists.
8. Create an implementation plan for the current phase.
9. Implement only the required phase.
10. Test it.
11. Update TODO.md.
12. Update documentation if architecture changed.

Never destroy working functionality merely to simplify implementation.

---

# 4. DO NOT FAKE FUNCTIONALITY

This project is intended to be a real working prototype.

NEVER:

- create fake anomaly scores
- hardcode model predictions
- create fake SHAP explanations
- create fake sensor health values
- use random values in production inference
- create dashboard placeholders that claim to be real
- claim a model is trained when it is not
- claim an API is connected when it is mocked
- claim real-time processing when data is only static
- claim a model has accuracy without evaluation

If something is not implemented:

Clearly mark it as:

NOT IMPLEMENTED

or

OPTIONAL / FUTURE WORK

Do not hide missing functionality.

---

# 5. RESEARCH/NOVELTY POSITION

Do NOT claim that basic ML anomaly detection is novel.

Existing approaches already include:

- threshold-based quality control
- temporal quality control
- persistence checks
- spatial/buddy checks
- autoencoders
- LSTM-based anomaly detection
- machine-learning anomaly detection
- sensor fault classification
- imputation

Therefore, SkyGuard's differentiation should focus on integrating these capabilities into a unified system.

Target differentiation:

1. Multi-signal anomaly fusion
2. Genuine meteorological event vs sensor fault discrimination
3. Explainable anomaly reasoning
4. Confidence/calibration
5. Sensor health scoring
6. Sensor degradation prediction
7. Optional corrected-value estimation
8. Real-time operation
9. Edge-friendly architecture
10. Unified operational dashboard

Do not present any one of these as automatically novel.
Novelty claims must be supported by research.

---

# 6. INPUT CONSTRAINT

The core system must work using ONLY:

- Temperature
- Atmospheric Pressure
- Relative Humidity

Do not make additional sensor parameters mandatory.

Optional metadata may include:

- timestamp
- station ID
- latitude
- longitude
- station elevation
- quality flags

But the core ML system must not depend on unavailable external variables.

---

# 7. DATA REQUIREMENTS

The system must support:

- CSV
- JSON
- Parquet where practical
- streaming input

Minimum required columns:

timestamp
temperature
pressure
humidity

Optional:

station_id
latitude
longitude
elevation

The system must validate:

- missing values
- duplicate timestamps
- invalid ranges
- timestamp ordering
- impossible values
- constant/frozen values
- malformed records

---

# 8. ANOMALY TYPES

The system should detect, where supported by data:

### A. Spike

Sudden unrealistic change.

Example:

20°C
21°C
22°C
55°C
22°C

---

### B. Dropout

Missing or invalid observation.

---

### C. Frozen Sensor

The same value repeats abnormally for an extended period.

Example:

27.4
27.4
27.4
27.4
27.4
...

---

### D. Drift

Slow abnormal deviation from expected behavior.

---

### E. Multivariate Inconsistency

Temperature, pressure and humidity relationships become inconsistent.

---

### F. Communication/Data Corruption

Malformed, duplicated, missing, delayed or structurally invalid observations.

---

### G. Genuine Meteorological Extreme

The system must NOT automatically label every extreme observation as a sensor fault.

It should determine whether the observation is:

- likely genuine event
- likely sensor anomaly
- uncertain

---

# 9. ML ARCHITECTURE

Use a layered approach.

## Layer 1 — Deterministic Quality Control

Examples:

- physical plausibility
- rate-of-change checks
- missing-value checks
- duplicate detection
- persistence/frozen-value checks

---

## Layer 2 — Statistical / Temporal Analysis

Possible methods:

- rolling statistics
- z-score
- robust z-score
- MAD
- EWMA
- seasonal baselines

Do not implement every method unnecessarily.

Select methods based on data and evaluation.

---

## Layer 3 — ML Anomaly Detection

Candidate models:

- Isolation Forest
- One-Class SVM
- Autoencoder
- LSTM/GRU Autoencoder
- Temporal model

Start with a strong baseline before adding complexity.

---

## Layer 4 — Multivariate Consistency

Analyze relationships among:

Temperature
Pressure
Humidity

The model should identify combinations that are unusual even if each individual value looks reasonable.

---

## Layer 5 — Anomaly Fusion

Combine signals from:

- deterministic QC
- statistical detection
- ML anomaly score
- temporal consistency
- multivariate consistency

Produce:

anomaly_score
confidence_score
severity

---

# 10. FAULT CLASSIFICATION

Where sufficient training/evaluation data exists, classify:

- normal
- spike
- dropout
- frozen
- drift
- multivariate inconsistency
- communication/data issue
- uncertain/genuine extreme

Do not claim perfect classification.

If training data is insufficient, use a hybrid rule + ML classifier and clearly document limitations.

---

# 11. EXPLAINABILITY

The system should explain every significant alert.

Example:

ANOMALY DETECTED

Temperature:
55°C

Pressure:
Abnormal deviation

Humidity:
98%

Reason:

- temperature increased 29°C within 5 minutes
- value deviates significantly from temporal baseline
- multivariate relationship is inconsistent
- ML anomaly score is high

Confidence:
94%

Classification:
Probable sensor anomaly

Possible methods:

- SHAP
- feature contribution analysis
- rule contribution
- model-specific explanations

Do not generate fake SHAP values.

---

# 12. SENSOR HEALTH

Create a sensor health score:

0–100

Possible interpretation:

90–100 = Excellent
75–89 = Good
50–74 = Degraded
25–49 = Poor
0–24 = Critical

Health should consider:

- anomaly frequency
- persistent faults
- drift
- missing data
- confidence-weighted anomalies
- recent behavior

Document exactly how the score is calculated.

Do not make the health score arbitrary.

---

# 13. DEGRADATION PREDICTION

This is an advanced phase.

The system may estimate:

- increasing anomaly frequency
- increasing drift
- declining data quality
- predicted maintenance requirement

Only implement predictive maintenance when sufficient historical information exists.

If there is not enough real data:

Use controlled simulated degradation experiments and explicitly label them as simulated.

---

# 14. IMPUTATION / CORRECTION

Optional.

If implemented, provide:

original_value
estimated_value
confidence
method

Never silently replace raw observations.

Always preserve:

RAW DATA

and

CORRECTED DATA

separately.

---

# 15. REAL-TIME SYSTEM

The system must eventually support:

Incoming AWS observation
        ↓
Validation
        ↓
Preprocessing
        ↓
Feature generation
        ↓
Anomaly inference
        ↓
Fault classification
        ↓
Confidence
        ↓
Sensor health
        ↓
Alert
        ↓
Dashboard

The architecture must support both:

1. historical batch processing
2. real-time streaming

---

# 16. BACKEND

Recommended:

Python
FastAPI

Backend responsibilities:

- dataset upload
- validation
- model inference
- real-time ingestion
- anomaly history
- sensor health
- alerts
- explanations
- model metadata
- evaluation metrics

Use a clean service architecture.

Do not put all logic inside API routes.

---

# 17. DATABASE

Use SQLite initially for simplicity and portability.

Structure should support:

- stations
- observations
- anomaly_events
- sensor_health
- model_runs
- alerts

Design the data layer so it can later migrate to PostgreSQL.

---

# 18. FRONTEND

The dashboard should be professional and operational.

Do NOT create a generic admin dashboard.

Core views:

### Overview

- active stations
- healthy stations
- degraded stations
- critical stations
- active alerts
- anomaly rate

### Live Monitoring

- temperature graph
- pressure graph
- humidity graph
- anomaly markers
- live status

### Alert Center

- severity
- timestamp
- station
- anomaly type
- confidence
- explanation

### Sensor Health

- health score
- trend
- fault history
- degradation indicators

### Event Detail

Show:

- raw values
- expected values
- anomaly score
- confidence
- contributing factors
- classification

### Data Explorer

Allow historical exploration.

---

# 19. UI DESIGN

The UI should feel like a professional meteorological operations platform.

Avoid:

- plain black screens
- generic CRUD interfaces
- excessive gradients
- unnecessary 3D effects
- meaningless animations

Use:

- clean information hierarchy
- cards
- charts
- status indicators
- alert severity
- responsive layouts
- clear typography
- accessible contrast

The dashboard should prioritize operational clarity.

---

# 20. TESTING

Testing is mandatory.

At minimum:

### Unit tests

- validation
- preprocessing
- feature generation
- anomaly scoring
- health calculation
- API services

### ML tests

- model loading
- inference
- expected input schema
- output schema
- anomaly score range

### Integration tests

Upload
→ processing
→ inference
→ database
→ API
→ frontend

### Edge cases

- missing values
- duplicated timestamps
- extreme values
- frozen values
- empty dataset
- malformed CSV
- missing columns

---

# 21. MODEL EVALUATION

Do NOT report only accuracy.

Evaluate:

- precision
- recall
- F1
- ROC-AUC where appropriate
- PR-AUC
- false positive rate
- false negative rate
- detection latency
- inference latency

For anomaly detection, prioritize:

- precision
- recall
- F1
- false alarm rate

because false alarms are a major operational problem.

---

# 22. DATA SPLITTING

Avoid random leakage.

For temporal data, prefer:

TRAIN
→ earlier time period

VALIDATION
→ later period

TEST
→ future period

Do not allow future observations into training.

---

# 23. EXPERIMENT TRACKING

Every meaningful model experiment should record:

- model
- parameters
- dataset version
- feature set
- training period
- validation period
- test period
- metrics
- artifact path

---

# 24. REPRODUCIBILITY

The project must contain:

- requirements/dependency file
- environment instructions
- training instructions
- inference instructions
- sample dataset
- sample configuration
- test instructions

Another developer should be able to clone the project and run it.

---

# 25. GIT RULES

Before major changes:

Check git status.

After meaningful completed work:

Commit changes with clear messages.

Example:

feat: implement multivariate anomaly fusion

fix: handle frozen sensor detection

test: add anomaly pipeline tests

docs: update architecture

Do not create enormous meaningless commits.

---

# 26. PHASE RULE

Do not jump ahead.

Complete phases in TODO.md sequentially.

At the end of every phase:

1. Run tests.
2. Verify functionality.
3. Update TODO.md.
4. Update documentation.
5. Report what was completed.
6. Identify remaining blockers.

---

# 27. DEFINITION OF DONE

SkyGuard is complete only when:

- historical data can be loaded
- data is validated
- anomalies can be detected
- anomaly types can be classified
- confidence is generated
- explanations are generated
- sensor health is calculated
- real-time ingestion works
- dashboard displays real data
- alerts work
- model evaluation exists
- tests pass
- documentation exists
- application can be run by another developer
- no core feature is fake or hardcoded
