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

    # Live-feed reading history, a store apart from the runs database. Empty: a local SQLite file. Deployed: the Tiger Cloud (TimescaleDB)
    # connection string, postgresql+asyncpg://...; kept in .env only. Keeps the rain fields only, for 90 days (the owner's choice, not a measured need).
    FEED_HISTORY_URL: str = ""
    FEED_HISTORY_PATH: str = "data/feed_history.db"
    FEED_HISTORY_RETENTION_DAYS: int = 90

    # PostgreSQL pool (ignored for SQLite). Small on purpose: a free Supabase pooler allows few connections.
    DB_POOL_SIZE: int = 3
    DB_MAX_OVERFLOW: int = 2

    # Weather Union live rain-gauge feed (backend/app/rainfall). Off unless a key AND a city are set.
    WEATHER_UNION_API_KEY: str = ""
    WEATHER_UNION_BASE_URL: str = "https://www.weatherunion.com/gw/weather/external/v0"
    WEATHER_UNION_CITY: str = ""                      # e.g. "Mumbai": poll the stations closest to the city's centre
    WEATHER_UNION_MAX_STATIONS: int = 9               # 9 stations x 96 polls/day = 864 calls, under the 1000/day free limit
    WEATHER_UNION_POLL_INTERVAL_SECONDS: float = 900.0
    WEATHER_UNION_DAILY_CALL_BUDGET: int = 900
    WEATHER_UNION_ACCUMULATION_MODE: str = "cumulative"   # cumulative | per_reading; the provider does not document it
    WEATHER_UNION_RAW_LOG_PATH: str = "data/weather_union_raw.jsonl"
    # The live feed's weather provider (Settings can override it): weather_union (rain gauges, a key is required) or open_meteo (hourly model
    # precipitation at each station's coordinates, no key needed; a commercial key is optional and uses the customer endpoint).
    WEATHER_PROVIDER: str = "weather_union"
    OPEN_METEO_BASE_URL: str = "https://api.open-meteo.com"
    OPEN_METEO_CUSTOMER_BASE_URL: str = "https://customer-api.open-meteo.com"
    OPEN_METEO_DAILY_CALL_BUDGET: int = 9000          # the free non-commercial allowance is 10,000 calls a day
    # Telemetry stream, ESP32 / MQTT source (slice S3b). Defaults only: Settings can override them; the password is a secret (write-only).
    MQTT_HOST: str = ""
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""
    # Keras reconstruction scorer (separate service, ml-service/scorer). Empty URL: no scorer, the checks still run. The secret lives in .env only.
    SCORER_URL: str = ""
    SCORER_SECRET: str = ""
    SCORER_TIMEOUT_SECONDS: float = 2.0
    SCORER_FALSE_ALARM_BUDGET: float = 0.001          # assumed: 1 flag per 1,000 clean scores
    SCORER_MIN_CLEAN_SCORES: int = 1000               # assumed: clean errors needed before a station/variable gets a threshold
    # The platform's own MCP endpoint for other people's agents (POST /api/mcp): read-only tools, a token per person made in Settings.
    MCP_AUDIT_LOG: str = "data/mcp_audit.jsonl"       # one JSON line per tool call (arguments capped, secrets redacted)
    MCP_RATE_PER_MINUTE: int = 120                    # tool calls per minute across all tokens
    MCP_ALLOWED_ORIGINS: str = ""                     # comma-separated browser origins allowed to call it; empty: none (agents send no Origin)
    MCP_MAX_TOKENS: int = 20                          # active tokens at most
    # The platform's own narrator for the AI chat and "Explain (AI)" when no NARRATOR_URL (or Gemini key) is set: the one in mcp-service, run in
    # this process. Grounded (fixed rules over the evidence and platform data, no language model) unless ANTHROPIC_API_KEY is set.
    NARRATOR_EMBEDDED: bool = True
    ANTHROPIC_API_KEY: str = ""
    NARRATOR_LLM_MODEL: str = "claude-sonnet-5-5"

    # AI narrator (built by the AI implementation team). NOT IMPLEMENTED on our side until they deliver: with NARRATOR_URL unset the
    # platform says "AI narrator not connected" and shows the rule-based baseline. The request and response shape is a proposal
    # (docs/contracts/narrator-request-v1.md) awaiting the team's confirmation. The token lives in .env only.
    NARRATOR_URL: str = ""
    NARRATOR_TOKEN: str = ""
    NARRATOR_TIMEOUT_SECONDS: float = 20.0

    # Interim LLM layer on Google Gemini (backend/app/validation/gemini.py), used while the AI team's narrator is not connected. A set
    # NARRATOR_URL always wins. The key lives in .env only. Only the evidence payload is sent, never the key or reviewer names.
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"       # live test 2026-11-20: lite 5 to 6 s per call; gemini-3.5-flash 22 to 56 s and one MAX_TOKENS failure (it spends tokens thinking). A setting on purpose: models are retired (2.5-flash answers 404 for new keys)
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"
    GEMINI_TIMEOUT_SECONDS: float = 90.0              # headroom for the slower gemini-3.5-flash (20 to 60 s); the lite default answers in about 5 s
    GEMINI_CALLS_PER_MINUTE: int = 10
    GEMINI_DAILY_CALL_BUDGET: int = 200

    # The platform's own agent (backend/app/agent, PROTOTYPE of a sandboxed bounded agent). Provider "gemini" reuses GEMINI_API_KEY; "none" switches
    # it off ("agent not connected": the rule-based baseline still explains). AGENT_MODEL empty: GEMINI_MODEL. Limits per turn are assumed config values.
    AGENT_PROVIDER: str = "gemini"
    AGENT_MODEL: str = ""
    AGENT_MAX_TOOL_CALLS: int = 6
    AGENT_TOKEN_BUDGET: int = 12000                   # assumed: the most INPUT tokens (estimated as characters / 4) one model call may be given, and the cap on output tokens
    AGENT_TIMEOUT_SECONDS: float = 90.0               # the whole turn

    # An exported score file (docs/contracts/score-export-v1.schema.json, written by ml-service/qc/score_export.py). Empty = no trained STNet scores
    # in the evidence. The file is read-only data; a station is mapped to its nearest cell within half a grid cell (ASSUMED stand-in mapping).
    SCORE_EXPORT_PATH: str = ""

    # A long random string for SCRIPTS (sent as X-Admin-Token); the dashboard signs in with ADMIN_EMAIL and ADMIN_PASSWORD below instead.
    # In .env only. Anyone who has this token can change the feed key and the narrator.
    ADMIN_TOKEN: str = ""

    # The admin sign-in of the dashboard (api/auth.py). The defaults are for local and demo use ONLY: anyone who knows them can sign in, so
    # set both in the server's environment on any public deployment (the server logs a warning at start-up when ENVIRONMENT=production and
    # the password is still the default). An empty ADMIN_PASSWORD switches the sign-in off.
    ADMIN_EMAIL: str = "admin@admin.com"
    ADMIN_PASSWORD: str = "admin"
    # When true (the default) every /api route except the sign-in itself needs a signed-in session: nobody reads any data without signing in.
    REQUIRE_LOGIN: bool = True

    # A READ-ONLY credential for an external reader such as the MCP server (idea from the rf pull request): sent as `Authorization: Bearer <token>`,
    # accepted only for GET requests under /api/validation/ and /api/places/, never for a write and never for another route. Empty = off.
    # In .env only. A long random string, different from ADMIN_TOKEN.
    EVIDENCE_API_TOKEN: str = ""

    # Kaggle API token (KGAT_...) for IMPORTING private datasets, used only when the caller sends none. Public datasets need no token at all.
    # Environment only, never a tracked file; leave empty and the page asks the visitor for a token when a dataset turns out to be private.
    KAGGLE_API_TOKEN: str = ""

    # Kaggle retraining (pipeline/kaggle_trigger.py): the owner's Kaggle account. Secrets: environment only, never a tracked file.
    KAGGLE_USERNAME: str = ""
    KAGGLE_KEY: str = ""

    # AWS retraining (pipeline/aws_trigger.py): region and S3 bucket used when a request brings none of its own. The credentials themselves come
    # from boto3's default chain (AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in the server's environment), never from a tracked file.
    AWS_REGION: str = "ap-southeast-2"
    AWS_TRAIN_BUCKET: str = ""

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

    # DATAMEND_ENV_FILE points at another .env (for example the main checkout's) so a second checkout can run with the same secrets without a copy.
    model_config = SettingsConfigDict(env_file=os.environ.get("DATAMEND_ENV_FILE") or ".env", extra="ignore")


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
