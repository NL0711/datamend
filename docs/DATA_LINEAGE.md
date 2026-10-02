# SkyGuard AI — Data Lineage & Provenance Tracking

## 1. Overview

In mission-critical meteorological quality-control platforms, every single observation, anomaly alert, and sensor health calculation must be traceable to its exact origin. SkyGuard AI provides complete **end-to-end data lineage** from raw sensor/provider ingestion to dashboard rendering.

---

## 2. Lineage Metadata Fields

Every record stored in `skyguard.db` and streamed over `/ws/live` contains:

| Field | Description | Example Values |
| :--- | :--- | :--- |
| `source_type` | Origin classification | `SIMULATED`, `EXTERNAL_API`, `PHYSICAL_AWS` |
| `source_id` | Specific adapter identifier | `diurnal_generator`, `open_meteo`, `esp32_bme280` |
| `provider` | External provider or sensor manufacturer | `Open-Meteo`, `SkyGuard-DiurnalEngine`, `Adafruit-BME280` |
| `device_id` | Hardware identifier / MAC address | `ESP32-DEV-BME280-01`, `AWS-ESP32-001` |
| `received_at` | Backend arrival timestamp (ISO-8601 UTC) | `2026-08-25T12:00:00.124Z` |
| `data_quality` | Initial ingestion validation | `GOOD`, `SUSPECT`, `QC_FLAGGED`, `INVALID` |

---

## 3. Provenance Verification Flow

```
+--------------------------+
| Telemetry Arrives        | (e.g. from Open-Meteo or ESP32)
+------------+-------------+
             |
             v
+--------------------------+
| Canonical Normalization  | -> Injects: source_type, source_id, provider, received_at
+------------+-------------+
             |
             v
+--------------------------+
| 5-Tier ML Quality Engine | -> Retains source provenance alongside inference results
+------------+-------------+
             |
             +-----------------------------+
             |                             |
             v                             v
+--------------------------+  +--------------------------+
| SQLite Persistence       |  | WebSocket Broadcast      |
| (observations & events)  |  | (InferenceResult packet) |
+--------------------------+  +------------+-------------+
                                           |
                                           v
                              +--------------------------+
                              | React UI Provenance View |
                              | (Shows active feed & ID) |
                              +--------------------------+
```
