# Industrial Energy Monitoring & Waste Detection System

A synthetic-data-driven industrial analytics application that correlates 15-minute machine telemetry, production output, time-of-use tariffs and weather to surface energy use, peak demand, idle-load opportunities and data-quality exceptions.

> **Data notice:** The included operational data is synthetic. Cost and savings values are estimates based on documented assumptions; they are not verified plant performance or guaranteed savings.

## Features
- Deterministic starter and full synthetic data profiles with a fixed seed.
- 15-minute energy readings, machines, meters, production batches, tariffs, shifts and weather.
- Separate anomaly ground-truth labels for evaluation; detection does not read the labels.
- Plant energy, cost, peak demand, idle energy and energy-intensity KPIs.
- Machine-wise energy and machine-output intensity.
- Weather-to-energy, demand, idle-load, production-output and intensity analysis on matched 6-hour UTC windows.
- Rule-based anomaly findings with evidence and investigation guidance.
- Idle-energy recommendations with transparent 25% scenario assumption and 30-day run-rate extrapolation.
- Streamlit dashboard filters for UTC date range, machine and anomaly severity.
- Production-batch energy allocation using overlap with 15-minute machine readings.
- FastAPI endpoints and SQLAlchemy/SQLite persistence.
- Data validation and pytest regression tests.

## Technology
Python, Pandas, NumPy, Streamlit, Plotly, FastAPI, SQLAlchemy, SQLite and Pytest.

## Setup (macOS)

```bash
cd ~/Downloads/"industrial-energy-monitoring 8"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Generate data

Starter profile (recommended for development):

```bash
python -m generator.generate_data --profile starter
```

Full profile (20 meters, 90 days, 15-minute cadence and 2,000 batches):

```bash
python -m generator.generate_data --profile full --output data/full
```

The generator writes source CSV files to `data/raw/` (no labels), a validation summary and reproducibility artifacts to `data/processed/`, and labels separately to `data/ground_truth/ground_truth.csv`. Source tables never contain issue or label columns. The full profile output is also committed under `data/full/` (raw, ground_truth, processed).

Shift IDs are derived from the UTC hour using the shift table (SH-001 06–14, SH-002 14–22, SH-003 22–06). Maintenance windows set `state = MAINTENANCE` on the affected machine's readings. Weather is recorded every 6 hours.

## Run tests and validation

```bash
pytest -q
python -m scripts.run_validation            # structural errors plus rule-based exceptions
python -m scripts.evaluate_detection        # detection vs ground truth -> data/processed/evaluation_metrics.json
python -m scripts.verify_reproducibility    # two same-seed builds compared by SHA-256
python -m scripts.verify_reproducibility --profile full --report data/full/processed/reproducibility_check.json
python -m scripts.run_validation --data-dir data/full/raw --output data/full/processed/validation_summary.json
```

`run_validation` reports structural errors (keys, foreign keys, enums, date order, shift calendar, interval reconciliation) separately from data-quality exceptions (excluded rows, register mismatches, tariff timezone mismatches). Exceptions do not make the dataset invalid.

## Export SQL seed data

Create a portable SQLite SQL dump from the source CSV tables. Ground-truth labels are excluded from the operational seed:

```bash
python -m scripts.export_sql --data-dir data/raw --output data/processed/industrial_energy_monitoring_seed.sql
python -m scripts.export_sql --data-dir data/full/raw --output data/full/processed/industrial_energy_monitoring_seed.sql
```

## Load SQLite

```bash
python -m app.database.init_db
python -m app.database.load_data
```

The loader replaces existing rows by default and reloads from `data/raw/`. The database file is `energy_monitoring.db` unless `DATABASE_URL` is set.

## Run the API

Terminal 1:

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`. Endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /health` | API health |
| `GET /validation` | Dataset validation |
| `GET /analytics/overview` | Plant energy KPIs |
| `GET /analytics/production` | Production batch efficiency |
| `GET /analytics/weather` | Weather joined to energy, demand, idle load, output and intensity in 6-hour UTC buckets |
| `GET /anomalies` | Anomaly summary; optional `?severity=HIGH` |
| `GET /recommendations` | Idle-energy opportunities |
| `GET /database/status` | SQLite connection and schema status |

The analytics API reads the generated CSV source data; SQLite is populated separately using the loader command.

## Run the dashboard

Terminal 2:

```bash
streamlit run app/dashboard.py
```

Use the sidebar to filter the UTC date range, machines and anomaly severity.

## Measurement assumptions
- `energy_kwh` is energy over an interval; `avg_power_kw` is interval-average demand.
- The expected reading cadence is 15 minutes (0.25 hours).
- Plant energy intensity divides valid meter energy by recorded actual output.
- Production-only intensity allocates valid machine energy to batch time windows and therefore excludes energy outside those windows. These two intensities are not interchangeable.
- Idle savings use 25% of observed valid idle energy as an illustrative scenario. Monthly values linearly extrapolate the selected observation period to 30 days.
- Valid rows exclude: non-kWh units, repeated reading_id (first occurrence kept), and machines not assigned to the reading's meter. Excluded rows are reported, not corrected.
- Costs use only tariff windows whose timezone matches the plant timezone. Energy in hours with no matching tariff is reported as unpriced, not costed.
- Detection reads source fields only. Labels in `data/ground_truth/` are used only by `scripts/evaluate_detection.py`.
- Evaluation measures how well the code implements the documented rules on synthetic data that was generated from the same rules. It is not evidence of accuracy on real plant data.
- Tariffs and weather are synthetic.
- Weather correlation is descriptive and does not establish causation.
- Weather observations are aligned to energy and production using matching 6-hour UTC buckets. Batch output is prorated across every bucket overlapped by a batch. Pearson coefficients are descriptive and are not causal estimates.
- The dashboard groups work into operator, maintenance/quality, production-planner and OT/IT-administrator perspectives. These are workflow views, not authenticated roles or access controls.

## Repository submission
Before submission, push the code to a public GitHub repository. This project folder has no configured remote; choose the repository target and publish it when ready. The project includes a README, source manifest, schema/data dictionary, validation summary, SQL seed export command and tests.
