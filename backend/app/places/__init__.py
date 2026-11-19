"""Place lookup (spec section 2, ticket t09): a stateless `locate(lat, lon)` plus the ScoreProvider seam. Stores nothing.

Gauges (uploads, Weather Union, the ISD replay) are the only inputs of the platform; no model product such as Open-Meteo is ever labelled
an observation.
"""
