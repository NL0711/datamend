/**
 * hardware/esp32/skyguard_aws/config.example.h
 * SkyGuard AI — ESP32 + BME280 AWS Station Configuration Template.
 * Copy this file to "config.h" and insert your local Wi-Fi and MQTT credentials.
 * DO NOT commit "config.h" with secrets to Git.
 */

#ifndef SKYGUARD_CONFIG_H
#define SKYGUARD_CONFIG_H

// ===========================================================================
// 1. Wi-Fi Access Point Credentials
// ===========================================================================
#define WIFI_SSID       "YOUR_WIFI_SSID"
#define WIFI_PASSWORD   "YOUR_WIFI_PASSWORD"

// ===========================================================================
// 2. MQTT Broker Credentials
// ===========================================================================
#define MQTT_BROKER     "broker.hivemq.com"   // Replace with your local/cloud broker IP/domain
#define MQTT_PORT       1883                  // Standard unencrypted MQTT port (or 8883 for TLS)
#define MQTT_USER       ""                    // Optional username
#define MQTT_PASSWORD   ""                    // Optional password

// ===========================================================================
// 3. Station & Hardware Identity
// ===========================================================================
#define STATION_ID      "AWS-ESP32-001"
#define DEVICE_ID       "ESP32-DEV-BME280-01"
#define FIRMWARE_VER    "1.2.0-PROD"

// Station Geographical Coordinates
#define STATION_LAT     18.5204
#define STATION_LON     73.8567
#define STATION_ELEV    560.0

// ===========================================================================
// 4. MQTT Topic Architecture
// ===========================================================================
#define TOPIC_TELEMETRY "skyguard/aws/AWS-ESP32-001/telemetry"
#define TOPIC_HEARTBEAT "skyguard/aws/AWS-ESP32-001/heartbeat"

// ===========================================================================
// 5. Sampling and Transmission Timing (Milliseconds)
// ===========================================================================
#define TELEMETRY_INTERVAL_MS   3000   // Publish weather telemetry every 3 seconds
#define HEARTBEAT_INTERVAL_MS   30000  // Publish health heartbeat every 30 seconds

// ===========================================================================
// 6. I2C Hardware Pin Mappings for ESP32
// ===========================================================================
#define I2C_SDA_PIN     21  // Standard ESP32 I2C SDA
#define I2C_SCL_PIN     22  // Standard ESP32 I2C SCL
#define BME280_I2C_ADDR 0x76 // 0x76 (SDO to GND) or 0x77 (SDO to VCC)

#endif // SKYGUARD_CONFIG_H
