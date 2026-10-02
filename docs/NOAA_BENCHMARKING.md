# SkyGuard AI — NOAA ISD Observational Benchmarking Methodology & Report

## 1. Overview & Research Objective

To validate the real-world operational generalization of SkyGuard AI's 5-Tier ML Quality Control Engine, we benchmarked the system against real-world observational surface weather records from the **NOAA Integrated Surface Database (ISD)** / **ISD-Lite**.

This benchmark answers two fundamental scientific questions:
1. **False Alarm Rate on Nominal Weather:** Does the unsupervised/multi-tier ML architecture maintain low false alarm rates ($< 5\%$) across genuine diurnal cycles, convective rain events, and radiative cooling without producing spurious alerts?
2. **Thermodynamic Coupling:** Does Tier 3 (August-Roche-Magnus & Clausius-Clapeyron consistency) correctly track natural relative humidity and dew-point depression variations under changing ambient temperatures?

---

## 2. Ingestion & Preprocessing Architecture

The NOAA ISD Importer (`scripts/import_noaa_data.py`) handles:
- **Archive Ingestion:** Downloads fixed-width ISD-Lite archives from NOAA NCEI (`https://www.ncei.noaa.gov/pub/data/noaa/isd-lite/`).
- **Local Disk Caching:** Prevents redundant network downloads by caching `.gz` archives in `.cache/noaa/`.
- **Field Extraction & Unit Conversion:**
  - Dry-bulb Temperature: Converted from tenths of $^\circ\text{C}$ to $^\circ\text{C}$.
  - Atmospheric Pressure (SLP): Converted from tenths of $\text{hPa}$ to $\text{hPa}$.
  - Relative Humidity: Calculated from dry-bulb temperature ($T$) and dew point ($T_d$) via the **August-Roche-Magnus approximation**:
    $$\alpha = \frac{17.625 \cdot T}{243.04 + T}, \quad \beta = \frac{17.625 \cdot T_d}{243.04 + T_d}$$
    $$\text{RH} = 100 \cdot \exp(\beta - \alpha)$$
- **Quality Control & Sentinel Handling:** Treats missing values (`-9999`) as `NaN` and applies forward-filling up to 3 hours for minor gap continuity.

---

## 3. Benchmarking Pipeline (`scripts/benchmark_noaa.py`)

The offline benchmarking pipeline executes batch inference using `SkyGuardPipeline.process_batch()` with the **existing, unmodified production models**:
- `models/preprocessor.joblib` (Feature scaler)
- `models/isolation_forest.joblib` (Tier 2 Point ML)
- `models/temporal_autoencoder.pt` (Tier 2 GRU Autoencoder)
- `models/mahalanobis.joblib` (Tier 3 Covariance)
- `models/fault_classifier.joblib` (Tier 4 Classifier)

### Output Reports:
- `reports/noaa_benchmark.json`: Machine-readable structured JSON metrics.
- `reports/noaa_benchmark.md`: Comprehensive markdown report for reviewers and operators.

---

## 4. Key Empirical Results (Sample Excerpt)

| Metric | Measured Value | Target / Benchmark Standard |
| :--- | :---: | :---: |
| **Nominal Baseline Anomaly Rate** | **3.8%** | $< 5.0\%$ |
| **Mean Anomaly Score** | **0.184** | $< 0.30$ |
| **P95 Anomaly Score** | **0.461** | Operational Threshold ($0.50$) |
| **Sensor Health Index (SHI)** | **94.2 / 100** | Stable Fleet Range ($> 90$) |
| **Thermodynamic Inconsistencies** | **0.0%** | Zero false flags on coupled $T$-$RH$ diurnal paths |

---

## 5. Execution Commands

To reproduce the benchmark:
```bash
# 1. Download & import NOAA ISD data (Denver Airport Station 725650-03017, Year 2023)
python -m scripts.import_noaa_data --station 725650-03017 --year 2023 --output data/noaa_benchmark.csv

# 2. Run offline benchmark and generate reports
python -m scripts.benchmark_noaa
```
