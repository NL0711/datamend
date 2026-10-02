/**
 * hardware/esp32/skyguard_aws/skyguard_aws.ino
 * SkyGuard AI — ESP32 Physical AWS Firmware for Adafruit BME280 Digital Sensor.
 * 
 * Features:
 * - Automatic Wi-Fi connection and reconnect state machine
 * - NTP Time Synchronization for true UTC timestamps
 * - Adafruit BME280 precision Temperature, Pressure, and Humidity sampling
 * - Non-blocking MQTT telemetry publishing to "skyguard/aws/{station_id}/telemetry"
 * - Health and device status heartbeat publishing to "skyguard/aws/{station_id}/heartbeat"
 * - Hardware NaN/Infinity safety filters
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>
#include <ArduinoJson.h>
#include <time.h>

#if __has_include("config.h")
  #include "config.h"
#else
  #include "config.example.h"
#endif

// ===========================================================================
// Hardware & Network Objects
// ===========================================================================
WiFiClient espClient;
PubSubClient mqttClient(espClient);
Adafruit_BME280 bme; // I2C

unsigned long lastTelemetryMillis = 0;
unsigned long lastHeartbeatMillis = 0;
unsigned long packetSequence = 0;
const char* ntpServer = "pool.ntp.org";

// ===========================================================================
// Helper: Obtain Current UTC Timestamp ISO-8601 String
// ===========================================================================
String getIsoTimestamp() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    return String(millis());
  }
  char timeStringBuff[30];
  strftime(timeStringBuff, sizeof(timeStringBuff), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);
  return String(timeStringBuff);
}

// ===========================================================================
// Wi-Fi Connection & Reconnection Management
// ===========================================================================
void setupWiFi() {
  delay(10);
  Serial.println();
  Serial.print("[WIFI] Connecting to SSID: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 25) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WIFI] Connected successfully!");
    Serial.print("[WIFI] IP Address: ");
    Serial.println(WiFi.localIP());

    // Initialize NTP time
    configTime(0, 0, ntpServer);
    Serial.println("[NTP] Time synchronization requested from pool.ntp.org");
  } else {
    Serial.println("\n[WIFI] Connection failed. Will retry in background loop.");
  }
}

// ===========================================================================
// MQTT Connection & Reconnection Management
// ===========================================================================
void reconnectMQTT() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  if (!mqttClient.connected()) {
    Serial.print("[MQTT] Attempting connection to broker ");
    Serial.print(MQTT_BROKER);
    Serial.print(":");
    Serial.println(MQTT_PORT);

    String clientId = "SkyGuard-" + String(STATION_ID) + "-" + String(random(0xffff), HEX);
    bool connected = false;

    if (strlen(MQTT_USER) > 0) {
      connected = mqttClient.connect(clientId.c_str(), MQTT_USER, MQTT_PASSWORD);
    } else {
      connected = mqttClient.connect(clientId.c_str());
    }

    if (connected) {
      Serial.println("[MQTT] Broker connected successfully!");
      // Publish initial boot heartbeat
      publishHeartbeat();
    } else {
      Serial.print("[MQTT] Connection failed, rc=");
      Serial.print(mqttClient.state());
      Serial.println(". Retrying on next loop cycle.");
    }
  }
}

// ===========================================================================
// Telemetry Publishing Function
// ===========================================================================
void publishTelemetry() {
  float temp = bme.readTemperature();       // Celsius (°C)
  float press = bme.readPressure() / 100.0F; // Convert Pa -> hPa
  float hum = bme.readHumidity();           // Relative Humidity (%)

  // Hardware sensor sanity check: reject NaN or non-physical read failures
  if (isnan(temp) || isnan(press) || isnan(hum) || press < 300.0 || press > 1200.0) {
    Serial.println("[SENSOR ERROR] Failed to read valid numerical data from BME280!");
    return;
  }

  packetSequence++;
  StaticJsonDocument<384> doc;
  doc["station_id"] = STATION_ID;
  doc["device_id"] = DEVICE_ID;
  doc["timestamp"] = getIsoTimestamp();
  doc["temperature"] = round(temp * 100.0) / 100.0;
  doc["pressure"] = round(press * 100.0) / 100.0;
  doc["humidity"] = round(hum * 100.0) / 100.0;
  doc["latitude"] = STATION_LAT;
  doc["longitude"] = STATION_LON;
  doc["elevation"] = STATION_ELEV;
  doc["sequence_number"] = packetSequence;
  doc["uptime_seconds"] = millis() / 1000;
  doc["rssi"] = WiFi.RSSI();

  char buffer[384];
  size_t len = serializeJson(doc, buffer);

  if (mqttClient.connected()) {
    mqttClient.publish(TOPIC_TELEMETRY, buffer, len);
    Serial.print("[TELEMETRY SENT] #");
    Serial.print(packetSequence);
    Serial.print(" -> T: ");
    Serial.print(temp);
    Serial.print("°C, P: ");
    Serial.print(press);
    Serial.print("hPa, RH: ");
    Serial.print(hum);
    Serial.println("%");
  } else {
    Serial.println("[WARN] MQTT not connected. Dropping telemetry packet.");
  }
}

// ===========================================================================
// Heartbeat & Device Health Publishing Function
// ===========================================================================
void publishHeartbeat() {
  StaticJsonDocument<256> doc;
  doc["station_id"] = STATION_ID;
  doc["device_id"] = DEVICE_ID;
  doc["timestamp"] = getIsoTimestamp();
  doc["firmware_version"] = FIRMWARE_VER;
  doc["uptime_seconds"] = millis() / 1000;
  doc["rssi"] = WiFi.RSSI();
  doc["free_heap"] = ESP.getFreeHeap();
  doc["sensor_model"] = "BME280";
  doc["status"] = "HEALTHY";

  char buffer[256];
  size_t len = serializeJson(doc, buffer);

  if (mqttClient.connected()) {
    mqttClient.publish(TOPIC_HEARTBEAT, buffer, len);
    Serial.println("[HEARTBEAT SENT] Station health status broadcasted.");
  }
}

// ===========================================================================
// Arduino Setup Function
// ===========================================================================
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=======================================================");
  Serial.println("SkyGuard AI — ESP32 AWS Meteorological Station v1.2.0");
  Serial.println("=======================================================");

  // Initialize I2C and BME280 sensor
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  bool bmeStatus = bme.begin(BME280_I2C_ADDR, &Wire);
  if (!bmeStatus) {
    Serial.println("[FATAL] Could not find valid BME280 sensor! Check wiring (SDA=21, SCL=22).");
  } else {
    Serial.println("[HARDWARE] BME280 Digital Sensor initialized successfully.");
    // Configure BME280 for Weather Monitoring mode (1x oversampling, forced mode)
    bme.setSampling(
      Adafruit_BME280::MODE_NORMAL,
      Adafruit_BME280::SAMPLING_X2, // Temperature oversampling
      Adafruit_BME280::SAMPLING_X16, // Pressure oversampling
      Adafruit_BME280::SAMPLING_X1, // Humidity oversampling
      Adafruit_BME280::FILTER_X16,
      Adafruit_BME280::STANDBY_MS_500
    );
  }

  // Setup Wi-Fi and MQTT client configuration
  setupWiFi();
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setBufferSize(512);
}

// ===========================================================================
// Arduino Main Loop Function
// ===========================================================================
void loop() {
  // Ensure Wi-Fi connection
  if (WiFi.status() != WL_CONNECTED) {
    setupWiFi();
  }

  // Ensure MQTT connection
  if (!mqttClient.connected()) {
    reconnectMQTT();
  }
  mqttClient.loop();

  unsigned long currentMillis = millis();

  // Periodic Telemetry Publishing
  if (currentMillis - lastTelemetryMillis >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryMillis = currentMillis;
    publishTelemetry();
  }

  // Periodic Device Health Heartbeat
  if (currentMillis - lastHeartbeatMillis >= HEARTBEAT_INTERVAL_MS) {
    lastHeartbeatMillis = currentMillis;
    publishHeartbeat();
  }
}
