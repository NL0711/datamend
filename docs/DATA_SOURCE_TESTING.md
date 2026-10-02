# SkyGuard AI — Data Source Automated & Integration Testing Report

## 1. Test Suite Summary

The automated test suite in `tests/test_data_sources.py` validates the complete lifecycle, canonical contract adherence, and failure handling across all three telemetry sources.

---

## 2. Test Cases Executed

| Test Identifier | Component Tested | Scenario | Result |
| :--- | :--- | :--- | :--- |
| `test_canonical_telemetry_valid` | Canonical Contract | Nominal observation converts to dictionary for ML pipeline | **PASS ✓** |
| `test_canonical_telemetry_range_validation` | Validation Safety | Rejects impossible temperatures (>100°C) and pressures (<100hPa) | **PASS ✓** |
| `test_simulated_data_source_lifecycle` | Simulated Adapter | Starts generator loop, emits canonical packets, stops cleanly | **PASS ✓** |
| `test_external_weather_mock_fetch` | Open-Meteo Adapter | Parses mocked Open-Meteo JSON into canonical telemetry format | **PASS ✓** |
| `test_external_weather_live_api_integration` | Live API Integration | Executes live HTTPS GET to Open-Meteo API for Delhi coordinates | **PASS ✓** |
| `test_physical_aws_normalization_and_virtual_packet` | Physical Adapter | Normalizes ESP32 BME280 MQTT payload into canonical schema | **PASS ✓** |
| `test_physical_aws_heartbeat` | Hardware Health | Tracks uptime, RSSI, free heap, and firmware version | **PASS ✓** |
| `test_data_source_manager_switching` | Source Manager | Switches active source dynamically without breaking ML engine | **PASS ✓** |

---

## 3. Execution Command

```bash
python -m pytest tests/test_data_sources.py -v
```

Output:
```
tests/test_data_sources.py::test_canonical_telemetry_valid PASSED        [ 12%]
tests/test_data_sources.py::test_canonical_telemetry_range_validation PASSED [ 25%]
tests/test_data_sources.py::test_simulated_data_source_lifecycle PASSED  [ 37%]
tests/test_data_sources.py::test_external_weather_mock_fetch PASSED      [ 50%]
tests/test_data_sources.py::test_external_weather_live_api_integration PASSED [ 62%]
tests/test_data_sources.py::test_physical_aws_normalization_and_virtual_packet PASSED [ 75%]
tests/test_data_sources.py::test_physical_aws_heartbeat PASSED           [ 87%]
tests/test_data_sources.py::test_data_source_manager_switching PASSED    [100%]
======================== 8 passed in 3.05s ========================
```
