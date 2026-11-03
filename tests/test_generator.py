import pandas as pd
from generator.generate_data import build
from scripts.verify_reproducibility import verify

INJECTED = {"METER_TOTAL_MISMATCH", "UNIT_KW_KWH_CONFUSION", "TARIFF_TIMEZONE_MISMATCH",
            "DUPLICATE_READING", "METER_MACHINE_HIERARCHY_VIOLATION"}

def test_starter_generator_is_repeatable(tmp_path):
    build("starter", 1234, tmp_path / "one")
    build("starter", 1234, tmp_path / "two")
    a = pd.read_csv(tmp_path / "one" / "raw" / "energy_readings.csv")
    b = pd.read_csv(tmp_path / "two" / "raw" / "energy_readings.csv")
    assert a.equals(b)

def test_generator_has_required_entities(tmp_path):
    build("starter", 20261022, tmp_path)
    required = ["plants", "meters", "machines", "energy_readings", "production_batches", "shifts",
                "tariffs", "weather_observations", "maintenance_events", "recommendations"]
    for name in required:
        assert (tmp_path / "raw" / f"{name}.csv").exists()
    assert (tmp_path / "ground_truth" / "ground_truth.csv").exists()

def test_source_tables_carry_no_labels(tmp_path):
    build("starter", 20261022, tmp_path)
    readings = pd.read_csv(tmp_path / "raw" / "energy_readings.csv")
    assert "issue_type" not in readings.columns
    assert not (tmp_path / "raw" / "issue_records.csv").exists()

def test_ground_truth_covers_every_injected_defect(tmp_path):
    build("starter", 20261022, tmp_path)
    gt = pd.read_csv(tmp_path / "ground_truth" / "ground_truth.csv")
    assert INJECTED <= set(gt.issue_type)

def test_shift_ids_follow_the_calendar(tmp_path):
    build("starter", 20261022, tmp_path)
    readings = pd.read_csv(tmp_path / "raw" / "energy_readings.csv")
    hours = pd.to_datetime(readings.timestamp_utc, utc=True).dt.hour
    assert (readings.loc[hours.between(6, 13), "shift_id"] == "SH-001").all()
    assert (readings.loc[hours.between(14, 21), "shift_id"] == "SH-002").all()
    assert readings.shift_id.notna().all()

def test_reproducibility_check_passes():
    assert verify("starter", 20261022)["identical"]
