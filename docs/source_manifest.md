# Source manifest

All generated data is synthetic and produced by `generator/generate_data.py`. No external datasets, personal information, or third-party operational records are used.

The generator uses the fixed default seed `20261022` and records the selected profile and SHA-256 hashes in `data/processed/reproducibility.json`. It also writes a structural validation report to `data/processed/validation_summary.json`. Full-profile equivalents are stored under `data/full/processed/`.

`scripts/export_sql.py` creates a SQL seed from `raw/*.csv` only. It deliberately excludes `ground_truth/` so evaluation labels cannot enter the application input tables.
