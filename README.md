# SkyGuard AI — Intelligent Real-Time Anomaly Detection & Sensor Health for AWS

**SkyGuard AI (v0.2.0 PRO)** is an intelligent real-time meteorological quality control, anomaly detection, fault classification, explainability, and sensor health monitoring platform for Automatic Weather Stations (AWS).

---

## 🌟 Key Capabilities

1. **Three Interchangeable Telemetry Feeds**:
   - **🟡 Simulated AWS:** Continuous diurnal radiation physics & Magnus-Tetens thermodynamics with live anomaly injection.
   - **🌐 Real External Weather Feed:** Open-Meteo REST API live surface observation ingestion with async polling and timeout backoff.
   - **📟 Real Physical AWS Sensor:** ESP32 microcontroller firmware sampling a Bosch BME280 precision sensor over MQTT.
2. **Canonical Telemetry Contract**: Normalizes $(T, P, RH)$ into a strict, validated schema preserving full source provenance and data lineage.
3. **5-Tier Machine Learning Pipeline**:
   - **Tier 1 (QC):** WMO physical bounds, rate-of-change, and frozen sensor checks.
   - **Tier 2 (ML Point & Temporal):** Scikit-Learn `IsolationForest` + PyTorch 2-layer GRU Autoencoder.
   - **Tier 3 (Multivariate):** Magnus-Tetens dew point consistency + Chi-Square Mahalanobis covariance distance.
   - **Tier 4 (Fusion & Classifier):** Convex fusion matrix + 7-Class Fault Taxonomy Random Forest Classifier.
   - **Tier 5 (Health & XAI):** Exponential Moving Average Sensor Health Index (SHI 0–100) + TreeSHAP feature attributions.
4. **Interactive Operations Dashboard**: High-density React + Tailwind UI with live 1-click source selector, latency counters, and WebSocket streaming.

---

## 🚀 Quickstart Guide

### 1. Backend Service
```bash
# Install Python dependencies
pip install -r requirements.txt

# Run Automated Test Suites
python -m pytest tests/test_data_sources.py tests/test_sanity.py -v

# Run Performance & Latency Benchmark
python -m scripts.benchmark_system

# Launch FastAPI Backend Server
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Operational Dashboard
```bash
cd frontend

# Install Node modules
npm install

# Start Vite Development Server
npm run dev

# Build Production Bundle
npm run build
```

---

## 📟 Physical AWS Hardware Setup (ESP32 + Bosch BME280)

1. **Hardware Connections**:
   - `VIN / VCC` $\rightarrow$ `3.3V`
   - `GND` $\rightarrow$ `GND`
   - `SDA` $\rightarrow$ `GPIO 21`
   - `SCL` $\rightarrow$ `GPIO 22`
2. **Firmware Flashing**:
   - Open `hardware/esp32/skyguard_aws/skyguard_aws.ino` in Arduino IDE.
   - Copy `config.example.h` to `config.h` and configure Wi-Fi SSID and MQTT broker.
   - Flash to DOIT ESP32 DevKit V1.
3. **MQTT Topics**:
   - Telemetry: `skyguard/aws/{station_id}/telemetry`
   - Heartbeat: `skyguard/aws/{station_id}/heartbeat`

---

## 📚 Technical Documentation

- [Data Source Architecture](docs/DATA_SOURCE_ARCHITECTURE.md)
- [External Weather Feed Setup (Open-Meteo)](docs/EXTERNAL_API_SETUP.md)
- [Physical AWS & ESP32 Hardware Guide](docs/PHYSICAL_AWS_SETUP.md)
- [MQTT Communication Protocol](docs/MQTT_PROTOCOL.md)
- [Data Lineage & Provenance Specification](docs/DATA_LINEAGE.md)
- [Automated Testing Report](docs/DATA_SOURCE_TESTING.md)
- [Master System Verification Audit](docs/FINAL_SYSTEM_VERIFICATION.md)
