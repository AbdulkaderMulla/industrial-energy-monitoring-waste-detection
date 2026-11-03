# Project progress

## Implemented
- [x] Deterministic starter/full synthetic data generator and separate ground truth.
- [x] Data validation and reconciliation rules.
- [x] Energy, demand, tariff cost, idle energy and energy-intensity analytics.
- [x] Machine-specific output denominator for machine energy intensity.
- [x] Rule-based anomaly detection and remediation guidance in the dashboard.
- [x] Idle-energy recommendations with clearly labelled 30-day run-rate estimates.
- [x] Streamlit dashboard with UTC date, machine and severity filters.
- [x] FastAPI overview, validation, anomalies, recommendations, production and database-status endpoints.
- [x] SQLAlchemy models and repeatable CSV-to-SQLite loading command.
- [x] Automated tests and documentation.

## Verified in the packaged environment
- `pytest -q`: 7 tests passed.
- Python compile check passed.
- SQLite loader smoke test inserted all available CSV tables (14 tables; 2,018 starter energy rows).

## Revision 2 (label separation and shift alignment)
- [x] Source tables carry no labels; injected defects and rule-derived waste labels are only in data/ground_truth/.
- [x] Detection reads source fields only; a test confirms results do not change when labels are altered.
- [x] Shared rules module (app/services/rules.py) for exclusions, tariff matching and pricing.
- [x] Shift IDs on readings and batches, validated against the shift calendar.
- [x] Maintenance windows produce MAINTENANCE states; weather observations every 6 hours.
- [x] Energy-intensity shift on configured machines, detected from batch-window energy per output unit.
- [x] Waste labels for high idle demand derived from the documented 30% rule.
- [x] Register mismatch is a 2% overstatement (replaces the fixed +12.5 kWh offset).
- [x] Evaluation script (precision/recall per label type) and reproducibility check script.
- [x] Full profile generated and committed under data/full/.

Full profile results (seed 20261022): 20 meters, 90 days, 172,662 energy rows (141 gap intervals), 2,000 batches, 77 labels; detection 77/77 matched, 0 false positives. Two same-seed builds are byte-identical.
Caveat: the labels and detection use the same documented rules, so this measures implementation fidelity on synthetic data, not accuracy on real plants.

## Before public submission
1. Run the starter profile locally and review the dashboard with the filters.
2. Run the full profile and assess local resource usage.
3. Review synthetic assumptions with the project guide; do not present synthetic results as real plant savings.
4. Add screenshots and push to a public GitHub repository as required by the project brief.
5. Deploy only after setting a persistent database and reviewing security, access control and secrets.

## Remediation update (2026-11-03)
- [x] Join weather, energy, demand, idle load and prorated batch output in matching six-hour UTC buckets; expose descriptive correlations in the dashboard and `GET /analytics/weather`.
- [x] Add separate operator, maintenance/quality, production-planner and OT/IT administrator dashboard perspectives. These are workflow views, not security roles.
- [x] Generate append-only machine status and telemetry transition events; validate event targets, states, ordering and old/new transition chains.
- [x] Expand validation to every source-table primary key and foreign key, plant consistency, effective-dated assignments, tariff/shift dates, cadence, state enums, batch output reconciliation and numeric domains.
- [x] Write `validation_summary.json` for starter and full profiles and add a CLI to refresh it.
- [x] Add a portable SQL seed exporter for all 14 operational tables; ground-truth labels are excluded. Starter/full SQL dumps are present under their respective `processed/` directories.
- [x] Apply effective dates when pricing readings and make starter CSV/JSON/SQL artifacts eligible for source control.
- [x] Regenerate both data profiles; the full profile still has 20 meters, 90 days, 2,000 batches and 77 labeled cases. Validation reports no structural errors. Same-seed reproducibility reports identical output for both profiles.
- [ ] Public GitHub publication remains pending: the supplied folder has no configured Git remote or repository target.

The pytest suite was not rerun during this remediation update.
