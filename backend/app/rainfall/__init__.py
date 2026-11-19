"""Rainfall path: live rain-gauge readings (Weather Union), daily totals and a one-station quality scorer.

Independent of the legacy temperature/pressure/humidity pipeline. Everything here is labelled by what it is:
the scorer uses rules and robust statistics (NOT a trained model), and rain_accumulation units/reset time are
UNCONFIRMED by the provider's documentation (see weather_union.py).
"""
