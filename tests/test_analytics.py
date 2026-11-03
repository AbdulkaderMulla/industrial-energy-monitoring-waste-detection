from generator.generate_data import build
from app.services.analytics import load_data, calculate_energy_metrics, detect_anomalies, build_recommendations, analyze_production_efficiency

def test_metrics_and_injected_defects_are_detected(tmp_path, monkeypatch):
    build("starter", 20261022, tmp_path / "data")
    data = load_data(tmp_path / "data" / "raw")
    metrics = calculate_energy_metrics(data)
    assert metrics["total_energy_kwh"] > 0
    assert metrics["peak_demand_kw"] > 0
    assert metrics["production_output_units"] > 0
    assert metrics["excluded_rows"]["DUPLICATE_READING"] == 1
    found = {x["issue_type"] for x in detect_anomalies(data)}
    for issue in ["DUPLICATE_READING", "UNIT_KW_KWH_CONFUSION", "METER_MACHINE_HIERARCHY_VIOLATION",
                  "METER_TOTAL_MISMATCH", "TARIFF_TIMEZONE_MISMATCH"]:
        assert issue in found
    assert build_recommendations(data)

def test_detection_ignores_labels(tmp_path):
    build("starter", 20261022, tmp_path / "data")
    before = detect_anomalies(load_data(tmp_path / "data" / "raw"))
    (tmp_path / "data" / "ground_truth" / "ground_truth.csv").write_text("corrupted,labels\n")
    after = detect_anomalies(load_data(tmp_path / "data" / "raw"))
    assert before == after

def test_machine_intensity_uses_machine_output(tmp_path):
    build("starter", 20261022, tmp_path / "data")
    data = load_data(tmp_path / "data" / "raw")
    for machine in calculate_energy_metrics(data)["machine_summary"]:
        output = machine.get("machine_output_units")
        if output:
            assert abs(machine["energy_intensity_kwh_per_unit"] - machine["energy_kwh"] / output) < 1e-10

def test_production_allocation_runs(tmp_path):
    build("starter", 20261022, tmp_path / "data")
    result = analyze_production_efficiency(load_data(tmp_path / "data" / "raw"))
    assert result["batch_detail"]
