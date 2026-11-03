from generator.generate_data import build
from validation.validate_data import validate

def test_starter_validation_has_no_structural_errors(tmp_path):
    build("starter", 20261022, tmp_path)
    result = validate(tmp_path / "raw")
    assert result["valid"], result["errors"]
    assert result["exceptions"]["excluded_readings"]["DUPLICATE_READING"] == 1
    assert result["exceptions"]["tariff_timezone_mismatches"] == ["TAR-2026-002"]
    assert result["exceptions"]["meter_register_mismatches"] == ["MTR-PLANT-001-001"]
