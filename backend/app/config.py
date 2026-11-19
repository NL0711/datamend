import os
from typing import List

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:
    from pydantic import BaseModel
    SettingsConfigDict = dict

    class BaseSettings(BaseModel):
        def __init__(self, **values):
            for k in self.model_fields.keys():
                if k in os.environ and k not in values:
                    values[k] = os.environ[k]
            super().__init__(**values)

class Settings(BaseSettings):
    PROJECT_NAME: str = "DataMend"
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
    # SQLite now (demo storage: resets on a free Render tier); PostgreSQL later (postgresql+asyncpg://...), the tables are portable.
    DATABASE_URL: str = "sqlite+aiosqlite:///./datamend.db"

    # Weather Union live rain-gauge feed (backend/app/rainfall). Off unless a key AND a city are set.
    WEATHER_UNION_API_KEY: str = ""
    WEATHER_UNION_BASE_URL: str = "https://www.weatherunion.com/gw/weather/external/v0"
    WEATHER_UNION_CITY: str = ""                      # e.g. "Mumbai": poll the stations closest to the city's centre
    WEATHER_UNION_MAX_STATIONS: int = 9               # 9 stations x 96 polls/day = 864 calls, under the 1000/day free limit
    WEATHER_UNION_POLL_INTERVAL_SECONDS: float = 900.0
    WEATHER_UNION_DAILY_CALL_BUDGET: int = 900
    WEATHER_UNION_ACCUMULATION_MODE: str = "cumulative"   # cumulative | per_reading; the provider does not document it
    WEATHER_UNION_RAW_LOG_PATH: str = "data/weather_union_raw.jsonl"

    # AI narrator (built by the AI implementation team). NOT IMPLEMENTED on our side until they deliver: with NARRATOR_URL unset the
    # platform says "AI narrator not connected" and shows the rule-based baseline. The request and response shape is a proposal
    # (docs/contracts/narrator-request-v1.md) awaiting the team's confirmation. The token lives in .env only.
    NARRATOR_URL: str = ""
    NARRATOR_TOKEN: str = ""
    NARRATOR_TIMEOUT_SECONDS: float = 20.0

    # Editing settings from the dashboard (api/settings.py) is DISABLED unless this is set; callers must send it as X-Admin-Token.
    # A long random string, in .env only. There are no user accounts: anyone who has this token can change the feed key and the narrator.
    ADMIN_TOKEN: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
