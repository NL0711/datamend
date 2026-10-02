# SkyGuard AI — MQTT Communication Protocol Specification

## 1. Topic Taxonomy

SkyGuard AI uses a hierarchical topic taxonomy for AWS telemetry and device diagnostics:

```
skyguard/
└── aws/
    └── {station_id}/
        ├── telemetry   (High-frequency sensor observations)
        └── heartbeat   (Low-frequency device diagnostics & health)
```

---

## 2. Topic Specifications

### A. Telemetry Topic: `skyguard/aws/{station_id}/telemetry`
- **Direction:** Hardware $\rightarrow$ SkyGuard Backend
- **QoS Level:** 1 (At least once delivery)
- **Publication Rate:** Every 3 seconds (configurable)
- **Payload Schema:**
```json
{
  "station_id": "AWS-ESP32-001",
  "device_id": "ESP32-DEV-BME280-01",
  "timestamp": "2026-08-25T12:00:00Z",
  "temperature": 26.42,
  "pressure": 1007.85,
  "humidity": 58.21,
  "latitude": 18.5204,
  "longitude": 73.8567,
  "elevation": 560.0,
  "sequence_number": 142,
  "uptime_seconds": 426,
  "rssi": -62
}
```

### B. Heartbeat Topic: `skyguard/aws/{station_id}/heartbeat`
- **Direction:** Hardware $\rightarrow$ SkyGuard Backend
- **QoS Level:** 1
- **Publication Rate:** Every 30 seconds
- **Payload Schema:**
```json
{
  "station_id": "AWS-ESP32-001",
  "device_id": "ESP32-DEV-BME280-01",
  "timestamp": "2026-08-25T12:00:00Z",
  "firmware_version": "1.2.0-PROD",
  "uptime_seconds": 426,
  "rssi": -62,
  "free_heap": 218440,
  "sensor_model": "BME280",
  "status": "HEALTHY"
}
```

---

## 3. Stale Detection & Timeout Handling

- If no message is received on either telemetry or heartbeat topics for **30 seconds**, the backend marks the station status as `🔴 DISCONNECTED` or `🟠 DEGRADED`.
- The dashboard displays a `⚠ STALE DATA` banner to prevent operators from viewing outdated measurements as live readings.
