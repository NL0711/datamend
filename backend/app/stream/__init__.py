"""Telemetry streams (slice S3a): the source interface, the manager, the simulator source, storage and the services the API uses.

Only the simulator source exists. Open-Meteo, Weather Union and ESP32 sources are NOT IMPLEMENTED (slice S3b); they register with the
manager the same way the simulator does (see runtime.py).
"""
