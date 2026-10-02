# SkyGuard AI — Physical ESP32 + BME280 Hardware Setup Guide

This guide describes how to assemble, flash, and connect a physical **Automatic Weather Station (AWS)** microstation running on an **ESP32** microcontroller and **Bosch BME280** sensor to SkyGuard AI via MQTT.

---

## 1. Hardware Bill of Materials (BOM)

| Component | Description | Reference / Link |
| :--- | :--- | :--- |
| **Microcontroller** | ESP32 NodeMCU / DevKit v1 (30-pin or 38-pin) | ESP-WROOM-32 |
| **Sensor Module** | Bosch BME280 (I2C Digital T, P, RH Sensor) | Adafruit / GY-BME280 |
| **Interconnects** | 4-pin Female-to-Female Jumper Wires | Standard 2.54mm pitch |
| **Power Supply** | Micro-USB Cable + 5V 1A Power Adapter | Standard USB |

---

## 2. Hardware Wiring Diagram (I2C)

Connect the **BME280** module to the **ESP32** using standard I2C pins:

```
+-------------------+                      +-------------------+
|  Bosch BME280     |                      |   ESP32 DevKit    |
|                   |                      |                   |
|  [VCC / VIN] -----+----------------------+-> [3.3V]          |
|  [GND] -----------+----------------------+-> [GND]           |
|  [SCL] -----------+----------------------+-> [GPIO 22 / SCL] |
|  [SDA] -----------+----------------------+-> [GPIO 21 / SDA] |
+-------------------+                      +-------------------+
```

> **Note:** Always power the BME280 from the **3.3V** pin, not 5V, unless your module explicitly includes an on-board 5V voltage regulator.

---

## 3. Arduino IDE / PlatformIO Setup

### Required Arduino Libraries:
1. **Adafruit BME280 Library** (by Adafruit) — Install via Library Manager.
2. **Adafruit Unified Sensor** (by Adafruit) — Install via Library Manager.
3. **PubSubClient** (by Nick O'Leary) — MQTT Client.
4. **ArduinoJson** (by Benoit Blanchon, v6.x or v7.x) — JSON serialization.

---

## 4. Firmware Configuration

1. Copy `config.example.h` to `config.h`:
   ```bash
   cp hardware/esp32/skyguard_aws/config.example.h hardware/esp32/skyguard_aws/config.h
   ```
2. Open `config.h` in Arduino IDE or VS Code:
   ```cpp
   #define WIFI_SSID       "YourWiFiNetwork"
   #define WIFI_PASSWORD   "YourWiFiPassword"
   #define MQTT_BROKER     "192.168.1.100"  // Local backend server IP or broker.hivemq.com
   #define MQTT_PORT       1883
   #define STATION_ID      "AWS-ESP32-001"
   ```
3. Connect the ESP32 via USB and select board: **"DOIT ESP32 DEVKIT V1"**.
4. Click **Upload**.

---

## 5. MQTT Topic Architecture & Payloads

### A. Live Telemetry Topic: `skyguard/aws/{station_id}/telemetry`
Published every **3 seconds**:
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

### B. Device Health Heartbeat Topic: `skyguard/aws/{station_id}/heartbeat`
Published every **30 seconds**:
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

## 6. SkyGuard Backend Integration

Once powered and connected to the MQTT broker, SkyGuard's `PhysicalAWSDataSource` automatically ingests, validates, and routes the telemetry into the 5-Tier ML Quality Control pipeline, displaying:
- 🟢 **PHYSICAL AWS — CONNECTED (ESP32-BME280)**
- Live calibrated charts with sub-30ms processing latency.
