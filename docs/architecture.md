# Architecture

```text
Deterministic synthetic generator
        |
        +--> raw CSV source records
        +--> isolated ground-truth labels
        |
Validation and reconciliation
        |
Analytics services (energy / tariffs / production / joined weather / idle)
        |
Rule-based anomaly detection and recommendation engine
        |
SQLAlchemy persistence (SQLite)
        |
FastAPI REST API ---------------- Streamlit + Plotly dashboard
```

## Layers

- `generator/`: creates parent entities before dependent records; injects explicit, labelled issue fixtures.
- `validation/`: checks every source key and FK, bridge/plant integrity, effective dates, state transition chains, enums, date ordering, cadence, arithmetic and output reconciliation; labeled source-quality exceptions are reported separately.
- `app/database/`: SQLAlchemy models, engine and persistence.
- `app/services/`: business calculations and decisions.
- `app/api/`: read-only REST endpoints over persisted data.
- `app/dashboard.py`: interactive user-facing analytics.
- `scripts/export_sql.py`: exports a portable SQL seed from operational source tables while excluding ground-truth labels.

The generated dataset is deterministic for a fixed seed/profile. All timestamps are UTC. The full profile contains 20 meters × 90 days × 96 intervals = 172,800 baseline meter intervals, plus separately marked exception fixtures.
