"""Export a SQLite-compatible SQL seed file from source CSV tables (ground truth excluded)."""
import argparse
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

from app.database.connection import Base
from app.database import models

TABLE_MODELS = [
    ("plants", models.Plant),
    ("meters", models.Meter),
    ("machines", models.Machine),
    ("shifts", models.Shift),
    ("tariffs", models.Tariff),
    ("meter_machine", models.MeterMachine),
    ("production_batches", models.ProductionBatch),
    ("batch_machine", models.BatchMachine),
    ("energy_readings", models.EnergyReading),
    ("weather_observations", models.WeatherObservation),
    ("maintenance_events", models.MaintenanceEvent),
    ("recommendations", models.Recommendation),
    ("meter_register_totals", models.MeterRegisterTotal),
    ("state_events", models.StateEvent),
]


def export_sql(data_dir=Path("data/raw"), output=Path("data/processed/industrial_energy_monitoring_seed.sql")):
    data_dir, output = Path(data_dir), Path(output)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    try:
        with engine.begin() as connection:
            for table_name, model in TABLE_MODELS:
                csv_path = data_dir / f"{table_name}.csv"
                if not csv_path.exists():
                    raise FileNotFoundError(f"Missing required source table: {csv_path}")
                frame = pd.read_csv(csv_path)
                records = frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")
                if records:
                    connection.execute(model.__table__.insert(), records)
        raw_connection = engine.raw_connection()
        try:
            dump = "\n".join(raw_connection.driver_connection.iterdump())
        finally:
            raw_connection.close()
    finally:
        engine.dispose()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "-- Generated from source CSV files by scripts/export_sql.py.\n"
        "-- Synthetic operational records only; ground_truth is deliberately excluded.\n"
        "PRAGMA foreign_keys = ON;\n"
        + dump + "\n"
    )
    return {"output": str(output), "tables": len(TABLE_MODELS), "source_dir": str(data_dir)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/industrial_energy_monitoring_seed.sql"))
    args = parser.parse_args()
    import json
    print(json.dumps(export_sql(args.data_dir, args.output), indent=2))


if __name__ == "__main__":
    main()
