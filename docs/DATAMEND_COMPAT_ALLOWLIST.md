# DataMend Rebrand — Compatibility Allowlist

(OpenSpec datamend-light-rebrand, task 3.4. Verified 2026-10-02.)

These identifiers intentionally still say `skyguard`/`SKYGUARD`. They are
unchanged for import, storage, wire-protocol, or historical compatibility.
Everything else user-facing was renamed to DataMend/datamend.

| Kept string | Where | Reason |
| :--- | :--- | :--- |
| `backend.*` module paths | all Python imports | renaming breaks every import, test, Dockerfile, and doc command |
| `skyguard.db` (+ `-shm`/`-wal`) | `config.py` default `DATABASE_URL`, repo files | existing local databases keep working as-is |
| `skyguard/aws/...` MQTT topics | `config.py`, firmware `config.example.h`, docs protocol pages | wire protocol shared with deployed ESP32 firmware |
| `SKYGUARD_CONFIG_H` include guards | `hardware/esp32/skyguard_aws/config.example.h` | file-scoped, harmless; firmware dir/`.ino` names kept with it |
| `skyguard_aws` dir / `.ino` name | `hardware/esp32/` | Arduino requires folder == sketch name |
| `SkyGuardPipeline` in `__pycache__/*.pyc` | stale tracked bytecode | interpreter recompiles from renamed sources (sources are newer); not user-facing |
| `openspec/changes/archive/**`, `.agents/**` | historical planning records and agent notes | history is not rewritten |
| `admin@datamend.ai` | `.env`, compose | already DataMend, no change needed |

Verification performed:
- `rg` sweep: no `SkyGuard`/`SKYGUARD` display strings remain outside this list
  (checked `backend/`, `frontend/src`, `scripts/`, `tests/`, `docs/`, root files).
- `DataMendPipeline` (renamed class) resolves consistently: definition, alias,
  and package exports all agree; backend import smoke + API test subset green.
- API contracts byte-identical: routes, schemas, and field names untouched
  (see `tests/test_task4_parity.py` passing).
