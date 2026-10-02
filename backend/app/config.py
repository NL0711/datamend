from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "SkyGuard AI"
    VERSION: str = "0.2.0"
    API_PREFIX: str = "/api"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5199",
        "http://127.0.0.1:5199",
        "http://localhost:3000",
    ]
    DATABASE_URL: str = "sqlite+aiosqlite:///./skyguard.db"

    # ML Pipeline defaults
    INFERENCE_WINDOW_SIZE: int = 30
    HEALTH_ROLLING_WINDOW: int = 288
    HEALTH_EMA_ALPHA: float = 0.10
    ANOMALY_THRESHOLD: float = 0.50

    # Data Source defaults
    DEFAULT_DATA_SOURCE: str = "SIMULATED"  # SIMULATED | EXTERNAL_API | PHYSICAL_AWS

    # External Weather API settings (Open-Meteo)
    EXTERNAL_WEATHER_PROVIDER: str = "open_meteo"
    EXTERNAL_WEATHER_BASE_URL: str = "https://api.open-meteo.com/v1/forecast"
    EXTERNAL_WEATHER_LATITUDE: float = 18.5204   # Pune, India (Standard reference observatory)
    EXTERNAL_WEATHER_LONGITUDE: float = 73.8567  # Pune, India
    EXTERNAL_WEATHER_STATION_ID: str = "PUNE-EXT-001"
    EXTERNAL_WEATHER_STATION_NAME: str = "Pune Meteorological Center"
    EXTERNAL_API_POLL_INTERVAL_SECONDS: float = 60.0
    EXTERNAL_API_TIMEOUT_SECONDS: float = 10.0

    # Physical AWS & MQTT settings
    MQTT_BROKER_HOST: str = "broker.hivemq.com"  # Public test broker default (configurable for private broker)
    MQTT_BROKER_PORT: int = 1883
    MQTT_USERNAME: Optional[str] = None
    MQTT_PASSWORD: Optional[str] = None
    MQTT_TLS: bool = False
    MQTT_TELEMETRY_TOPIC: str = "skyguard/aws/+/telemetry"
    MQTT_HEARTBEAT_TOPIC: str = "skyguard/aws/+/heartbeat"
    PHYSICAL_AWS_TIMEOUT_SECONDS: float = 30.0
    PHYSICAL_DEFAULT_STATION_ID: str = "AWS-ESP32-001"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
