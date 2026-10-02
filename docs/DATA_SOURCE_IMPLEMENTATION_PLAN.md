# SkyGuard AI — Three-Source Telemetry Architecture & Implementation Plan

## 1. Executive Summary

SkyGuard AI is being extended from a single synthetic simulator into a **multi-source real-time quality-control platform** that supports three interchangeable, production-grade telemetry sources:
1. **SIMULATED AWS TELEMETRY** (Diurnal sinusoidal solar cycle + programmatic anomaly injector)
2. **REAL EXTERNAL WEATHER DATA FEED** (Live real-time meteorological feed via Open-Meteo REST API)
3. **REAL PHYSICAL AWS / ESP32 SENSOR DATA** (Physical ESP32 microcontroller with BME280 sensor communicating over MQTT)

---

## 2. Core Architectural Principle: Data Source Abstraction Layer

All incoming data sources pass through a unified **DataSource Adapter** that normalizes measurements into a canonical contract before reaching the existing ML quality-control and health pipeline:

```
                                +-----------------------------+
                                |         SKYGUARD AI         |
                                +--------------+--------------+
                                               |
                                     DATA SOURCE MANAGER
                                 (backend/app/sources/manager.py)
                                               |
                +------------------------------+------------------------------+
                |                              |                              |
                v                              v                              v
       +------------------+          +-------------------+          +-------------------+
       |    SIMULATED     |          |   EXTERNAL API    |          |   PHYSICAL AWS    |
       |                  |          |                   |          |                   |
       | DiurnalGenerator |          | Open-Meteo API    |          | ESP32 + BME280    |
       | AnomalyInjector  |          | Polling Adapter   |          | MQTT Client       |
       +--------+---------+          +---------+---------+          +---------+---------+
                |                              |                              |
                +------------------------------+------------------------------+
                                               |
                                               v
                                  CANONICAL TELEMETRY CONTRACT
                                 (backend/app/schemas/canonical.py)
                                               |
                                               v
                                  DATA VALIDATION & INGESTION
                                (backend/app/services/ingestion.py)
                                               |
                                               v
                                   EXISTING 5-TIER ML ENGINE
                                  (backend/app/ml/pipeline.py)
                                               |
                      +------------------------+------------------------+
                      |                        |                        |
                      v                        v                        v
             SQLITE PERSISTENCE        WEBSOCKET STREAMING          TREESHAP XAI
              (skyguard.db)                (/ws/live)              (tier5_explain)
                      |                        |                        |
                      +------------------------+------------------------+
                                               |
                                               v
                                  REACT OPERATIONAL DASHBOARD
                                    (frontend/src/App.tsx)
```

---

## 3. Canonical Telemetry Schema Specification

All sources normalize into a single canonical Pydantic model (`backend/app/schemas/canonical.py`):

```python
class DataSourceType(str, Enum):
    SIMULATED = "SIMULATED"
    EXTERNAL_API = "EXTERNAL_API"
    PHYSICAL_AWS = "PHYSICAL_AWS"

class CanonicalTelemetry(BaseModel):
    station_id: str                       # e.g., "AWS-001", "PUNE-EXT-001", "AWS-ESP32-001"
    timestamp: datetime                   # ISO 8601 UTC timestamp
    temperature: float                    # Mandatory: Celsius (°C)
    pressure: float                       # Mandatory: Atmospheric Pressure in hPa
    humidity: float                       # Mandatory: Relative Humidity (%)
    source_type: DataSourceType           # SIMULATED | EXTERNAL_API | PHYSICAL_AWS
    source_id: str                        # e.g., "diurnal_generator", "open_meteo", "esp32_bme280"
    provider: Optional[str] = None        # e.g., "Open-Meteo", "SkyGuard-Hardware"
    latitude: Optional[float] = None      # Decimal degrees
    longitude: Optional[float] = None     # Decimal degrees
    elevation: Optional[float] = None     # Meters above sea level
    unit_system: str = "metric"
    sequence_number: Optional[int] = None
    received_at: datetime
    data_quality: str = "GOOD"
    connectivity_status: str = "CONNECTED"
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)
```

---

## 4. Subsystem Implementation Breakdown

### Phase 1: Data Source Abstraction Layer
* `backend/app/sources/base.py`: Abstract `BaseDataSource` interface (`start()`, `stop()`, `get_status()`, `health_check()`).
* `backend/app/sources/manager.py`: `DataSourceManager` singleton managing active source, graceful switching, telemetry dispatch, and stale data monitoring.
* `backend/app/sources/simulated_source.py`: Adapter wrapping existing `SimulationService` and `DiurnalGenerator`.

### Phase 2: Real External Weather Data Feed (Open-Meteo)
* `backend/app/sources/external_source.py`: Asynchronous polling worker querying Open-Meteo REST API (`https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,surface_pressure`).
* Configurable polling interval (`EXTERNAL_API_POLL_INTERVAL_SECONDS`, default: 60s), timeouts, exponential backoff, boundary validation, and stale detection.
* Real location mapping (default: Pune / Delhi / Mumbai or custom configurable coordinates via `.env`).

### Phase 3: Physical AWS Backend (MQTT & Hardware Ingestion)
* `backend/app/sources/physical_source.py`: MQTT subscriber client (`paho-mqtt` / async loop) listening on:
  - Telemetry: `skyguard/aws/+/telemetry`
  - Heartbeat: `skyguard/aws/+/heartbeat`
* Configurable broker host, port, credentials, TLS.
* 30-second heartbeat timeout: marks station `DISCONNECTED` if hardware goes offline.

### Phase 4: ESP32 Firmware Package
* `hardware/esp32/skyguard_aws/`:
  - `skyguard_aws.ino`: Arduino/ESP32 C++ firmware with Wi-Fi reconnection, Adafruit BME280 I2C sensor polling, JSON serialization, and MQTT publishing.
  - `config.example.h`: Wi-Fi and MQTT credentials template.
  - `README.md`: Hardware wiring schematics, pinout guide (SDA=21, SCL=22), and deployment guide.

### Phase 5: Database & API Extensions
* Extend SQLite models (`Observation`, `AnomalyEvent`) with `source_type`, `source_id`, `provider` fields with safe backwards-compatible defaults.
* REST Endpoints in `backend/app/api/routes.py`:
  - `GET /api/data-sources`: List available sources with live connection status.
  - `GET /api/data-sources/status`: Current active source status and telemetry age.
  - `POST /api/data-sources/select`: Controlled source switching (`{"source_type": "EXTERNAL_API"}`).
  - `GET /api/data-sources/external/preview`: Direct live fetch preview from Open-Meteo.

### Phase 6: Frontend Data Source Control & Status Badges
* Add **Data Source Selector & Status Control** in the header/dashboard:
  - 🟢 `PHYSICAL AWS — CONNECTED` (or 🔴 `PHYSICAL AWS — DISCONNECTED`)
  - 🟢 `EXTERNAL FEED — CONNECTED (Open-Meteo)` (or 🔴 `EXTERNAL FEED — DISCONNECTED`)
  - 🟡 `SIMULATED LIVE (Diurnal Generator)`
* Real-time packet age indicator: detects stale data if data age $> 60\text{s}$.
* Data Lineage indicator showing exact sensor/provider source for each reading.

### Phase 7: Testing & Verification
* Full unit and integration test suite in `tests/test_data_sources.py`.
* Live Open-Meteo external integration test.
* Virtual MQTT physical hardware packet test.
* Regression test run across all 20 existing test modules.

---

## 5. Risk Assessment & Mitigation

| Risk | Mitigation Strategy |
| :--- | :--- |
| **Breaking existing ML pipeline** | ML pipeline continues to receive standard `Dict[str, float]` with `temperature`, `pressure`, `humidity`. Zero changes to ML tier mathematics. |
| **API rate limiting on Open-Meteo** | Default polling set to 60s with local caching; fails gracefully to `DEGRADED` without breaking UI. |
| **Silent fallback falsification** | Strictly forbidden. If Open-Meteo or ESP32 is offline, status visibly displays `DISCONNECTED` with exact error message. |
| **Database migration issues** | Use SQLite `ALTER TABLE` / default column values so existing historical rows remain valid. |
