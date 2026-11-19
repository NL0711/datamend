import json
import os
from typing import Annotated, List

from pydantic import field_validator

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

try:
    # pydantic-settings >= 2.7: stop it from JSON-decoding list env vars before our validator runs.
    from pydantic_settings import NoDecode
    _OriginList = Annotated[List[str], NoDecode]
except ImportError:
    _OriginList = List[str]

class Settings(BaseSettings):
    PROJECT_NAME: str = "DataMend"
    VERSION: str = "0.2.0"
    API_PREFIX: str = "/api"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: _OriginList = [
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

    # NOAA ISD India replay (backend/app/rainfall/isd_replay.py): real station rainfall to Aug 2025, labelled REPLAY. Off unless set.
    # Non-US ISD data is subject to WMO Resolution 40 (no redistribution): turn it on only for a demonstration you are entitled to run.
    ISD_REPLAY_ON_START: bool = False                 # fetch and store the replay at launch when none is stored yet
    ISD_REPLAY_STATIONS: str = ""                     # comma-separated ISD ids (USAF-WBAN); empty = the built-in list of 14 city stations

    # AI narrator (built by the AI implementation team). NOT IMPLEMENTED on our side until they deliver: with NARRATOR_URL unset the
    # platform says "AI narrator not connected" and shows the rule-based baseline. The request and response shape is a proposal
    # (docs/contracts/narrator-request-v1.md) awaiting the team's confirmation. The token lives in .env only.
    NARRATOR_URL: str = ""
    NARRATOR_TOKEN: str = ""
    NARRATOR_TIMEOUT_SECONDS: float = 20.0

    # Editing settings from the dashboard (api/settings.py) is DISABLED unless this is set; callers must send it as X-Admin-Token.
    # A long random string, in .env only. There are no user accounts: anyone who has this token can change the feed key and the narrator.
    ADMIN_TOKEN: str = ""
    # The admin sign-in of the dashboard (api/auth.py). The defaults are for local and demo use ONLY: anyone who knows them can sign in, so
    # set both in the server's environment on any public deployment. An empty ADMIN_PASSWORD switches the sign-in off.
    ADMIN_EMAIL: str = "admin@admin.com"
    ADMIN_PASSWORD: str = "admin"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v):
        """Accept a JSON list, a comma-separated string, or a single URL (trailing slashes stripped)."""
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("["):
                v = json.loads(s)
            else:
                v = [p for p in s.split(",")]
        if isinstance(v, (list, tuple)):
            return [str(p).strip().strip("\"'").rstrip("/") for p in v if str(p).strip().strip("\"'")]
        return v

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _async_database_url(cls, v):
        """Accept the string a host hands out (postgres://... ?sslmode=require) and make it work with the async driver."""
        return normalize_database_url(v) if isinstance(v, str) else v

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def normalize_database_url(url: str) -> str:
    """postgres:// and postgresql:// become postgresql+asyncpg://; asyncpg does not know sslmode, so sslmode=X becomes ssl=X. SQLite is untouched."""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
    s = url.strip().strip("\"'")
    for prefix in ("postgres://", "postgresql://"):
        if s.startswith(prefix):
            s = "postgresql+asyncpg://" + s[len(prefix):]
    if s.startswith("postgresql+asyncpg://"):
        parts = urlsplit(s)
        query = [("ssl" if k == "sslmode" else k, val) for k, val in parse_qsl(parts.query, keep_blank_values=True)]
        s = urlunsplit(parts._replace(query=urlencode(query)))
    return s


settings = Settings()
