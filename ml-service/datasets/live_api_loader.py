"""
Live API dataset acquisition (Objective #1 in the proposal: "unified
pipeline for ingesting uploaded and live time-series datasets").

This adds a second acquisition path alongside TSDB (benchmark datasets)
and file upload: pulling a fresh time series directly from a free public
API at request time. Two sources are wired up to start:

- "weather": Open-Meteo (no API key required) - hourly weather for a
  given latitude/longitude.
- "crypto": CoinGecko (no API key required) - historical daily price/
  market-cap/volume for a given coin.

Both return the same shape as the rest of the pipeline expects: a
DataFrame indexed by a `timestamp` column plus one or more numeric
signal columns, so it can flow straight into profiling, rule-based
validation, and anomaly detection.
"""

from __future__ import annotations

from typing import Literal, Optional

import pandas as pd
import requests

LiveSource = Literal["weather", "crypto", "generic"]

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
_COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/{id}/market_chart"


class LiveApiError(RuntimeError):
    """Raised when a live API cannot be reached or returns bad data."""


def fetch_generic(
    url: str,
    api_key: Optional[str] = None,
    json_path: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch data from a generic URL, optionally with a Bearer token API key.
    If the array of data is nested, json_path can specify the key (e.g. 'data.series').
    Expects the final array to contain objects with a 'timestamp' or 'time' key.
    """
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        raise LiveApiError(f"Failed to fetch generic API data: {exc}") from exc
        
    data = payload
    if json_path:
        parts = json_path.split('.')
        for p in parts:
            if p and isinstance(data, dict):
                data = data.get(p, {})
                
    if not isinstance(data, list):
        raise LiveApiError(f"Expected a JSON array, got {type(data).__name__}. Check json_path.")
        
    df = pd.DataFrame(data)
    
    # Try to find a time column
    time_col = None
    for col in ["timestamp", "time", "date"]:
        if col in df.columns:
            time_col = col
            break
            
    if not time_col:
        raise LiveApiError(f"Could not find a 'timestamp', 'time', or 'date' column in API response.")
        
    if time_col != "timestamp":
        df = df.rename(columns={time_col: "timestamp"})
        
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def fetch_weather(
    latitude: float = 19.076,
    longitude: float = 72.8777,
    past_days: int = 7,
    hourly_vars: Optional[list[str]] = None,
) -> pd.DataFrame:
    """
    Fetch recent hourly weather for a location from Open-Meteo.
    Defaults to Mumbai, IN. No API key required.
    """
    hourly_vars = hourly_vars or [
        "temperature_2m", "relative_humidity_2m", "precipitation",
        "wind_speed_10m", "surface_pressure",
    ]
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(hourly_vars),
        "past_days": past_days,
        "timezone": "auto",
    }
    try:
        resp = requests.get(_OPEN_METEO_URL, params=params, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        raise LiveApiError(f"Failed to fetch weather data: {exc}") from exc

    hourly = payload.get("hourly")
    if not hourly or "time" not in hourly:
        raise LiveApiError("Open-Meteo response missing 'hourly' data")

    df = pd.DataFrame(hourly)
    df = df.rename(columns={"time": "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def fetch_crypto(
    coin_id: str = "bitcoin",
    vs_currency: str = "usd",
    days: int = 30,
) -> pd.DataFrame:
    """
    Fetch daily market data (price, market cap, volume) for a coin from
    CoinGecko. No API key required for this endpoint's free tier.
    """
    params = {"vs_currency": vs_currency, "days": days}
    try:
        resp = requests.get(_COINGECKO_URL.format(id=coin_id), params=params, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        raise LiveApiError(f"Failed to fetch crypto data: {exc}") from exc

    if "prices" not in payload:
        raise LiveApiError(f"CoinGecko response missing 'prices' (got: {list(payload.keys())})")

    prices = pd.DataFrame(payload["prices"], columns=["timestamp_ms", "price"])
    market_caps = pd.DataFrame(payload.get("market_caps", []), columns=["timestamp_ms", "market_cap"])
    volumes = pd.DataFrame(payload.get("total_volumes", []), columns=["timestamp_ms", "volume"])

    df = prices
    if not market_caps.empty:
        df = df.merge(market_caps, on="timestamp_ms", how="left")
    if not volumes.empty:
        df = df.merge(volumes, on="timestamp_ms", how="left")

    df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit="ms")
    df = df.drop(columns=["timestamp_ms"])
    cols = ["timestamp"] + [c for c in df.columns if c != "timestamp"]
    return df[cols]


def fetch_live_dataset(source: LiveSource, **kwargs) -> pd.DataFrame:
    """Dispatch to the right live-source fetcher by name."""
    if source == "weather":
        return fetch_weather(**kwargs)
    if source == "crypto":
        return fetch_crypto(**kwargs)
    if source == "generic":
        return fetch_generic(**kwargs)
    raise LiveApiError(f"Unknown live source: {source!r}")
