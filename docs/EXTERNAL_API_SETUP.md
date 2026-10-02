# SkyGuard AI — External Weather Feed Setup Guide (Open-Meteo)

## 1. Overview

SkyGuard AI integrates with **Open-Meteo**, a high-resolution, open-source global numerical weather API that provides real-time meteorological station observations and surface assimilation without requiring proprietary API keys.

---

## 2. Configuration Parameters

External feed settings are configured via environment variables in `.env`:

```env
# External Weather Feed Configuration
DEFAULT_DATA_SOURCE=EXTERNAL_API
EXTERNAL_WEATHER_PROVIDER=open_meteo
EXTERNAL_WEATHER_BASE_URL=https://api.open-meteo.com/v1/forecast
EXTERNAL_WEATHER_LATITUDE=18.5204
EXTERNAL_WEATHER_LONGITUDE=73.8567
EXTERNAL_WEATHER_STATION_ID=PUNE-EXT-001
EXTERNAL_WEATHER_STATION_NAME=Pune Meteorological Center
EXTERNAL_API_POLL_INTERVAL_SECONDS=60.0
EXTERNAL_API_TIMEOUT_SECONDS=10.0
```

---

## 3. Supported Locations

You can monitor any global coordinate by changing `EXTERNAL_WEATHER_LATITUDE` and `EXTERNAL_WEATHER_LONGITUDE`:

| City | Latitude | Longitude | Station ID |
| :--- | :--- | :--- | :--- |
| **Pune, India** | `18.5204` | `73.8567` | `PUNE-EXT-001` |
| **New Delhi, India** | `28.6139` | `77.2090` | `DELHI-EXT-001` |
| **Mumbai, India** | `18.9220` | `72.8347` | `MUMBAI-EXT-001` |
| **Tokyo, Japan** | `35.6762` | `139.6503` | `TOKYO-EXT-001` |
| **Geneva, Switzerland (WMO HQ)** | `46.2044` | `6.1432` | `GENEVA-EXT-001` |

---

## 4. Normalization and Field Mapping

Incoming Open-Meteo JSON payload is parsed and validated by `ExternalWeatherDataSource` (`backend/app/sources/external_source.py`):

| Open-Meteo Field | Canonical Telemetry Field | Target Unit |
| :--- | :--- | :--- |
| `current.temperature_2m` | `temperature` | Celsius (°C) |
| `current.surface_pressure` | `pressure` | Hectopascals (hPa) |
| `current.relative_humidity_2m` | `humidity` | Percentage (%) |
| `current.time` | `timestamp` | ISO-8601 UTC |
| `latitude`, `longitude`, `elevation` | `latitude`, `longitude`, `elevation` | Degrees / Meters |

---

## 5. Live Test Querying

You can execute an immediate on-demand live test fetch from the terminal or REST API:

```bash
curl -X GET "http://localhost:8000/api/data-sources/external/preview"
```

Response:
```json
{
  "success": true,
  "provider": "Open-Meteo",
  "telemetry": {
    "station_id": "PUNE-EXT-001",
    "timestamp": "2026-08-25T12:00:00Z",
    "temperature": 27.8,
    "pressure": 1008.2,
    "humidity": 65.4,
    "source_type": "EXTERNAL_API",
    "source_id": "open_meteo",
    "provider": "Open-Meteo",
    "connectivity_status": "CONNECTED"
  }
}
```
