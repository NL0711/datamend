# SkyGuard AI — Physical AWS Hardware & MQTT Setup Guide

## 1. Overview

SkyGuard AI connects to real **Automatic Weather Stations (AWS)** microstations using the **ESP32** microcontroller and **Bosch BME280** precision environmental sensor over standard **MQTT** message queues.

---

## 2. Hardware Architecture

```
+---------------------+
| Bosch BME280 Sensor | (Digital Temperature, Pressure, Humidity via I2C)
+----------+----------+
           | (SDA: GPIO 21, SCL: GPIO 22, 3.3V, GND)
           v
+---------------------+
|  ESP32 Microstation | (Arduino C++ Firmware, NTP UTC Sync, JSON Serializer)
+----------+----------+
           | (Wi-Fi 802.11 b/g/n)
           v
+---------------------+
|     MQTT Broker     | (e.g. broker.hivemq.com / Mosquitto on port 1883)
+----------+----------+
           | (Topic: skyguard/aws/+/telemetry)
           v
+---------------------+
| SkyGuard AI Backend | (PhysicalAWSDataSource Adapter -> 5-Tier ML Pipeline)
+---------------------+
```

---

## 3. Configuration Parameters in `.env`

```env
# Physical AWS & MQTT Configuration
MQTT_BROKER_HOST=broker.hivemq.com
MQTT_BROKER_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
MQTT_TLS=false
MQTT_TELEMETRY_TOPIC=skyguard/aws/+/telemetry
MQTT_HEARTBEAT_TOPIC=skyguard/aws/+/heartbeat
PHYSICAL_AWS_TIMEOUT_SECONDS=30.0
PHYSICAL_DEFAULT_STATION_ID=AWS-ESP32-001
```

---

## 4. Hardware Assembly & Flashing

1. Wire the **BME280** module to the **ESP32**:
   - `VIN / VCC` $\rightarrow$ `3.3V`
   - `GND` $\rightarrow$ `GND`
   - `SDA` $\rightarrow$ `GPIO 21`
   - `SCL` $\rightarrow$ `GPIO 22`
2. Open `hardware/esp32/skyguard_aws/skyguard_aws.ino` in Arduino IDE.
3. Copy `config.example.h` to `config.h` and configure your Wi-Fi SSID and MQTT broker.
4. Select Board: **DOIT ESP32 DEVKIT V1** and flash to the microcontroller.

---

## 5. Virtual Hardware Packet Testing

If physical ESP32 microcontrollers are not currently powered on, you can test the physical pipeline via HTTP:

```bash
curl -X POST "http://localhost:8000/api/data-sources/physical/virtual-packet" \
     -H "Content-Type: application/json" \
     -d '{"station_id": "AWS-ESP32-001", "temperature": 26.4, "pressure": 1007.8, "humidity": 58.2, "device_id": "ESP32-DEV-01"}'
```
