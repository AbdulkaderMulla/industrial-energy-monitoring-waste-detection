from pathlib import Path
import pandas as pd
from app.database.connection import Base, engine, SessionLocal
from app.database import models

TABLE_MODEL = {
    "plants": models.Plant,
    "meters": models.Meter,
    "machines": models.Machine,
    "meter_machine": models.MeterMachine,
    "energy_readings": models.EnergyReading,
    "production_batches": models.ProductionBatch,
    "batch_machine": models.BatchMachine,
    "shifts": models.Shift,
    "tariffs": models.Tariff,
    "weather_observations": models.WeatherObservation,
    "maintenance_events": models.MaintenanceEvent,
    "recommendations": models.Recommendation,
    "meter_register_totals": models.MeterRegisterTotal,
    "state_events": models.StateEvent,
}

def load_csv_data(data_dir=None, replace=True):
    data_dir = Path(data_dir) if data_dir is not None else Path(__file__).resolve().parents[2] / "data" / "raw"
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    inserted = {}
    try:
        # Delete in reverse dependency order when reloading.
        if replace:
            for model in [
                models.StateEvent, models.MeterRegisterTotal, models.Recommendation,
                models.MaintenanceEvent, models.WeatherObservation, models.Tariff,
                models.Shift, models.BatchMachine, models.ProductionBatch,
                models.EnergyReading, models.MeterMachine, models.Machine,
                models.Meter, models.Plant
            ]:
                session.query(model).delete()
            session.commit()
        for table, model in TABLE_MODEL.items():
            path = data_dir / f"{table}.csv"
            if not path.exists():
                continue
            frame = pd.read_csv(path)
            frame = frame.astype(object).where(pd.notna(frame), None)
            records = frame.to_dict(orient="records")
            if records:
                session.bulk_insert_mappings(model, records)
            inserted[table] = len(records)
        session.commit()
        return inserted
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    import json
    print(json.dumps(load_csv_data(), indent=2))
