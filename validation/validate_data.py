"""Validate source structure and report intentional data-quality exceptions separately."""
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import pandas as pd

from app.services.rules import (
    CANONICAL_UNIT, RUNNING_STATES, clean_readings,
    register_mismatches, tariff_mismatches,
)

REQUIRED_TABLES = [
    "plants", "meters", "machines", "meter_machine", "energy_readings",
    "production_batches", "batch_machine", "shifts", "tariffs",
    "weather_observations", "maintenance_events", "recommendations",
    "state_events", "meter_register_totals",
]

PRIMARY_KEYS = {
    "plants": "plant_id", "meters": "meter_id", "machines": "machine_id",
    "meter_machine": "assignment_id", "energy_readings": "row_id",
    "production_batches": "batch_id", "batch_machine": "batch_machine_id",
    "shifts": "shift_id", "tariffs": "tariff_id",
    "weather_observations": "weather_id", "maintenance_events": "event_id",
    "recommendations": "recommendation_id", "state_events": "state_event_id",
    "meter_register_totals": "meter_id",
}

REQUIRED_FIELDS = {
    "plants": ["plant_id", "name", "location", "timezone", "status"],
    "meters": ["meter_id", "plant_id", "meter_name", "unit", "cadence_minutes", "status"],
    "machines": ["machine_id", "plant_id", "machine_name", "machine_type", "rated_power_kw", "status"],
    "meter_machine": ["assignment_id", "meter_id", "machine_id", "effective_from"],
    "energy_readings": ["row_id", "reading_id", "meter_id", "timestamp_utc", "energy_kwh", "avg_power_kw", "unit", "state"],
    "production_batches": ["batch_id", "plant_id", "shift_id", "start_utc", "end_utc", "planned_output_units", "actual_output_units", "status"],
    "batch_machine": ["batch_machine_id", "batch_id", "machine_id", "output_units"],
    "shifts": ["shift_id", "plant_id", "shift_name", "start_time", "end_time", "effective_from"],
    "tariffs": ["tariff_id", "plant_id", "tariff_name", "start_hour_utc", "end_hour_utc", "rate_inr_per_kwh", "effective_from", "timezone"],
    "weather_observations": ["weather_id", "plant_id", "timestamp_utc", "temperature_c", "humidity_pct", "condition"],
    "maintenance_events": ["event_id", "machine_id", "event_type", "start_utc", "status"],
    "recommendations": ["recommendation_id", "machine_id", "created_utc", "reason", "baseline_kwh", "expected_savings_kwh", "expected_savings_inr", "priority", "status"],
    "state_events": ["state_event_id", "entity_type", "entity_id", "new_state", "event_utc", "actor", "reason"],
    "meter_register_totals": ["meter_id", "register_total_kwh"],
}


def _date_series(frame, column):
    return pd.to_datetime(frame[column], utc=True, errors="coerce")


def validate(data_dir=Path("data/raw")):
    data_dir = Path(data_dir)
    missing_files = [name for name in REQUIRED_TABLES if not (data_dir / f"{name}.csv").exists()]
    if missing_files:
        return {
            "valid": False,
            "errors": [f"Missing required CSV: {name}.csv" for name in missing_files],
            "exceptions": {},
            "counts": {},
        }

    tables = {name: pd.read_csv(data_dir / f"{name}.csv") for name in REQUIRED_TABLES}
    errors = []

    def check(condition, message):
        try:
            passed = bool(condition)
        except (TypeError, ValueError):
            passed = False
        if not passed:
            errors.append(message)

    missing_columns = []
    for table, fields in REQUIRED_FIELDS.items():
        missing_columns.extend(f"{table}.{field}" for field in fields if field not in tables[table].columns)
    if missing_columns:
        return {
            "valid": False,
            "errors": ["Missing required columns: " + ", ".join(missing_columns)],
            "exceptions": {},
            "counts": {name: int(len(frame)) for name, frame in tables.items()},
        }

    # Non-null business keys and primary-key uniqueness for every source entity/table.
    for table, key in PRIMARY_KEYS.items():
        values = tables[table][key]
        check(values.notna().all() and values.astype(str).str.strip().ne("").all(), f"Null/blank primary key in {table}.{key}")
        check(not values.duplicated().any(), f"Duplicate primary key in {table}.{key}")
    for table, fields in REQUIRED_FIELDS.items():
        check(tables[table][fields].notna().all().all(), f"Null required field in {table}")

    # Foreign-key integrity. Optional FKs are checked when populated.
    fk_specs = [
        ("meters", "plant_id", "plants", "plant_id"),
        ("machines", "plant_id", "plants", "plant_id"),
        ("meter_machine", "meter_id", "meters", "meter_id"),
        ("meter_machine", "machine_id", "machines", "machine_id"),
        ("energy_readings", "meter_id", "meters", "meter_id"),
        ("energy_readings", "machine_id", "machines", "machine_id"),
        ("energy_readings", "shift_id", "shifts", "shift_id"),
        ("production_batches", "plant_id", "plants", "plant_id"),
        ("production_batches", "shift_id", "shifts", "shift_id"),
        ("batch_machine", "batch_id", "production_batches", "batch_id"),
        ("batch_machine", "machine_id", "machines", "machine_id"),
        ("shifts", "plant_id", "plants", "plant_id"),
        ("tariffs", "plant_id", "plants", "plant_id"),
        ("weather_observations", "plant_id", "plants", "plant_id"),
        ("maintenance_events", "machine_id", "machines", "machine_id"),
        ("recommendations", "machine_id", "machines", "machine_id"),
        ("state_events", "entity_id", "machines", "machine_id"),
        ("meter_register_totals", "meter_id", "meters", "meter_id"),
    ]
    for child, field, parent, parent_key in fk_specs:
        values = set(tables[child][field].dropna().astype(str))
        parents = set(tables[parent][parent_key].dropna().astype(str))
        check(values <= parents, f"{child}.{field} FK violation against {parent}.{parent_key}")

    # Enums, numeric domains, and cross-entity plant consistency.
    enum_specs = [
        ("plants", "status", {"ACTIVE", "INACTIVE"}),
        ("meters", "status", {"ACTIVE", "INACTIVE"}),
        ("machines", "status", {"ACTIVE", "INACTIVE"}),
        ("energy_readings", "state", RUNNING_STATES),
        ("production_batches", "status", {"PLANNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"}),
        ("maintenance_events", "status", {"PLANNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"}),
        ("recommendations", "priority", {"LOW", "MEDIUM", "HIGH"}),
        ("recommendations", "status", {"OPEN", "ACCEPTED", "REJECTED", "COMPLETED"}),
        ("weather_observations", "condition", {"CLEAR", "CLOUDY", "RAINY"}),
    ]
    for table, field, allowed in enum_specs:
        check(set(tables[table][field].dropna().astype(str)) <= allowed, f"Invalid enum in {table}.{field}")

    readings = tables["energy_readings"]
    for field in ["energy_kwh", "avg_power_kw"]:
        values = pd.to_numeric(readings[field], errors="coerce")
        check(values.notna().all() and np.isfinite(values).all(), f"Non-numeric/non-finite values in energy_readings.{field}")
        check(values.ge(0).all(), f"Negative values in energy_readings.{field}")
    for table, field in [("machines", "rated_power_kw"), ("tariffs", "rate_inr_per_kwh"),
                         ("batch_machine", "output_units"), ("production_batches", "actual_output_units"),
                         ("production_batches", "planned_output_units"), ("meter_register_totals", "register_total_kwh"),
                         ("recommendations", "baseline_kwh"), ("recommendations", "expected_savings_kwh"),
                         ("recommendations", "expected_savings_inr")]:
        values = pd.to_numeric(tables[table][field], errors="coerce")
        check(values.notna().all() and np.isfinite(values).all() and values.ge(0).all(), f"Invalid nonnegative numeric values in {table}.{field}")
    check(pd.to_numeric(tables["meters"].cadence_minutes, errors="coerce").gt(0).all(), "Non-positive meter cadence")
    humidity = pd.to_numeric(tables["weather_observations"].humidity_pct, errors="coerce")
    check(humidity.between(0, 100).all(), "Weather humidity outside 0-100")
    temperature = pd.to_numeric(tables["weather_observations"].temperature_c, errors="coerce")
    check(temperature.notna().all() and np.isfinite(temperature).all(), "Invalid weather temperature")
    for timezone_name in list(tables["plants"].timezone.dropna().astype(str)) + list(tables["tariffs"].timezone.dropna().astype(str)):
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            errors.append(f"Unknown IANA timezone: {timezone_name}")

    meter_plant = tables["meters"].set_index("meter_id").plant_id.astype(str).to_dict()
    machine_plant = tables["machines"].set_index("machine_id").plant_id.astype(str).to_dict()
    shift_plant = tables["shifts"].set_index("shift_id").plant_id.astype(str).to_dict()
    batch_plant = tables["production_batches"].set_index("batch_id").plant_id.astype(str).to_dict()
    check(all(meter_plant.get(str(r.meter_id)) == machine_plant.get(str(r.machine_id))
              for r in tables["meter_machine"].itertuples()), "Meter-machine assignment crosses plant boundaries")
    check(all(meter_plant.get(str(r.meter_id)) == machine_plant.get(str(r.machine_id))
              for r in readings.dropna(subset=["machine_id"]).itertuples()), "Energy reading meter and machine cross plant boundaries")
    check(all(batch_plant.get(str(r.batch_id)) == machine_plant.get(str(r.machine_id))
              for r in tables["batch_machine"].itertuples()), "Batch-machine assignment crosses plant boundaries")
    check(all(shift_plant.get(str(r.shift_id)) == str(r.plant_id)
              for r in tables["production_batches"].dropna(subset=["shift_id"]).itertuples()), "Batch shift belongs to another plant")

    # Parse all event/effective timestamps, and check date ordering.
    date_specs = {
        "energy_readings": ["timestamp_utc"],
        "production_batches": ["start_utc", "end_utc"],
        "maintenance_events": ["start_utc"],
        "weather_observations": ["timestamp_utc"],
        "recommendations": ["created_utc"],
        "state_events": ["event_utc"],
        "meter_machine": ["effective_from", "effective_to"],
        "shifts": ["effective_from", "effective_to"],
        "tariffs": ["effective_from", "effective_to"],
    }
    parsed = {}
    for table, fields in date_specs.items():
        for field in fields:
            values = tables[table][field]
            optional = field == "effective_to" or (table == "maintenance_events" and field == "end_utc")
            parsed[(table, field)] = _date_series(tables[table], field)
            valid_dates = parsed[(table, field)].notna() if not optional else (values.isna() | parsed[(table, field)].notna())
            check(valid_dates.all(),
                  f"Invalid timestamp in {table}.{field}")

    check((parsed[("production_batches", "end_utc")] > parsed[("production_batches", "start_utc")]).all(), "Batch end must be after start")
    maintenance_end = _date_series(tables["maintenance_events"], "end_utc") if "end_utc" in tables["maintenance_events"] else pd.Series(pd.NaT, index=tables["maintenance_events"].index)
    maintenance_start = parsed[("maintenance_events", "start_utc")]
    check((maintenance_end.isna() | (maintenance_end > maintenance_start)).all(), "Maintenance end must be after start")
    for table, start_field in [("meter_machine", "effective_from"), ("shifts", "effective_from"), ("tariffs", "effective_from")]:
        end_field = "effective_to"
        if end_field in tables[table]:
            start_values, end_values = parsed[(table, start_field)], parsed[(table, end_field)]
            check((end_values.isna() | (end_values > start_values)).all(), f"{table} effective_to must be after effective_from")

    tariff_starts = pd.to_numeric(tables["tariffs"].start_hour_utc, errors="coerce")
    tariff_ends = pd.to_numeric(tables["tariffs"].end_hour_utc, errors="coerce")
    check(tariff_starts.between(0, 23).all() and tariff_ends.between(1, 24).all() and
          (tariff_starts < tariff_ends).all(), "Tariff hour window must be a non-wrapping interval inside 0–24")
    tariffs = tables["tariffs"].copy()
    tariffs["_from"] = parsed[("tariffs", "effective_from")]
    tariffs["_to"] = parsed[("tariffs", "effective_to")]
    for plant_id, group in tariffs.groupby("plant_id"):
        rows = group.to_dict(orient="records")
        for i, left in enumerate(rows):
            for right in rows[i + 1:]:
                date_overlap = (pd.isna(left["_to"]) or right["_from"] < left["_to"]) and (pd.isna(right["_to"]) or left["_from"] < right["_to"])
                hour_overlap = max(int(left["start_hour_utc"]), int(right["start_hour_utc"])) < min(int(left["end_hour_utc"]), int(right["end_hour_utc"]))
                same_zone = str(left["timezone"]) == str(right["timezone"])
                check(not (date_overlap and hour_overlap and same_zone), f"Overlapping effective tariff windows for plant {plant_id}")

    # Prevent overlapping duplicate meter-machine assignment windows.
    assignments = tables["meter_machine"].copy()
    assignments["_from"] = parsed[("meter_machine", "effective_from")]
    assignments["_to"] = parsed[("meter_machine", "effective_to")]
    check(not assignments.duplicated(["meter_id", "machine_id", "effective_from"]).any(), "Duplicate meter-machine assignment start")
    for _, group in assignments.sort_values("_from").groupby(["meter_id", "machine_id"]):
        previous_end = None
        for _, row in group.iterrows():
            if previous_end is not None:
                check(row["_from"] >= previous_end, "Overlapping effective-dated meter-machine assignments")
            previous_end = row["_to"] if pd.notna(row["_to"]) else pd.Timestamp.max.tz_localize("UTC")

    # Cadence, interval arithmetic, and shift-calendar alignment.
    timestamps = parsed[("energy_readings", "timestamp_utc")]
    cadence = readings.meter_id.astype(str).map(tables["meters"].set_index("meter_id").cadence_minutes.astype(int).to_dict())
    check(((timestamps.dt.minute % cadence == 0) & (timestamps.dt.second == 0) & (timestamps.dt.microsecond == 0)).all(), "Reading timestamps do not follow each meter cadence")
    energy = pd.to_numeric(readings.energy_kwh, errors="coerce")
    power = pd.to_numeric(readings.avg_power_kw, errors="coerce")
    meter_cadence = tables["meters"].set_index("meter_id").cadence_minutes.astype(float).to_dict()
    interval_hours = readings.meter_id.astype(str).map(meter_cadence) / 60.0
    check((np.abs(energy - power * interval_hours) <= 1e-4).all(), "Interval energy does not reconcile with average power times meter cadence")

    shifts = tables["shifts"].copy()
    shift_start = parsed[("shifts", "effective_from")]
    shift_end = parsed[("shifts", "effective_to")]
    shift_windows = []
    for i, row in shifts.iterrows():
        try:
            start_hour, start_minute = map(int, str(row.start_time).split(":")[:2])
            end_hour, end_minute = map(int, str(row.end_time).split(":")[:2])
            check(0 <= start_hour < 24 and 0 <= end_hour <= 24 and 0 <= start_minute < 60 and 0 <= end_minute < 60,
                  "Invalid shift time window")
            shift_windows.append((str(row.shift_id), start_hour * 60 + start_minute,
                                  end_hour * 60 + end_minute, shift_start.loc[i], shift_end.loc[i]))
        except (ValueError, TypeError):
            errors.append("Invalid shift time window")

    def expected_shift(stamp):
        if pd.isna(stamp):
            return None
        minute = stamp.hour * 60 + stamp.minute
        matches = []
        for shift_id, start_minute, end_minute, effective_from, effective_to in shift_windows:
            date_active = stamp >= effective_from and (pd.isna(effective_to) or stamp < effective_to)
            in_window = (start_minute <= minute < end_minute) if start_minute < end_minute else (minute >= start_minute or minute < end_minute)
            if date_active and in_window:
                matches.append(shift_id)
        return matches[0] if len(matches) == 1 else None

    expected_reading_shifts = timestamps.map(expected_shift)
    check((readings.shift_id.isna() | readings.shift_id.astype(str).eq(expected_reading_shifts.astype(str))).all(), "Energy-reading shift IDs do not match the effective shift calendar")
    batch_starts = parsed[("production_batches", "start_utc")]
    expected_batch_shifts = batch_starts.map(expected_shift)
    check((tables["production_batches"].shift_id.astype(str) == expected_batch_shifts.astype(str)).all(), "Production-batch shift IDs do not match the effective shift calendar")

    # Bridge totals must reconcile to the parent batch output.
    bridged_output = tables["batch_machine"].groupby("batch_id").output_units.sum()
    for batch in tables["production_batches"].itertuples():
        check(float(bridged_output.get(batch.batch_id, 0)) == float(batch.actual_output_units),
              f"Batch output does not reconcile for {batch.batch_id}")

    # Append-only state history: event targets, valid domains, order, and old/new transitions.
    state_events = tables["state_events"].copy()
    state_events["_event_time"] = parsed[("state_events", "event_utc")]
    machine_ids = set(tables["machines"].machine_id.astype(str))
    state_events["entity_type"] = state_events.entity_type.astype(str)
    check(set(state_events.entity_type) <= {"MACHINE_STATUS", "MACHINE_OPERATING_STATE"}, "Unsupported state event entity_type")
    check(set(state_events.entity_id.astype(str)) <= machine_ids, "State event references unknown machine")
    check(all((row.new_state in {"ACTIVE", "INACTIVE"}) if row.entity_type == "MACHINE_STATUS"
              else (row.new_state in RUNNING_STATES) for row in state_events.itertuples()), "State event has an invalid state for its entity type")
    for (entity_type, entity_id), group in state_events.sort_values("_event_time").groupby(["entity_type", "entity_id"]):
        previous = None
        previous_time = None
        for _, row in group.iterrows():
            if previous is None:
                check(pd.isna(row["old_state"]) or str(row["old_state"]).strip() == "", f"First state event must have blank old_state for {entity_type}/{entity_id}")
            else:
                check(str(row["old_state"]) == str(previous), f"State event transition chain is broken for {entity_type}/{entity_id}")
                check(row["_event_time"] > previous_time, f"State events are not strictly ordered for {entity_type}/{entity_id}")
            previous, previous_time = row["new_state"], row["_event_time"]

    # Data-quality exceptions remain visible and do not make the baseline structurally invalid.
    valid_readings, excluded = clean_readings(readings, tables["meter_machine"])
    plant_timezone = str(tables["plants"].timezone.iloc[0])
    excluded_counts = {str(k): int(v) for k, v in excluded.exclusion_reason.value_counts().items()}
    effective_hierarchy_violations = []
    assignment_windows = {}
    for _, row in assignments.iterrows():
        key = (str(row["meter_id"]), str(row["machine_id"]))
        assignment_windows.setdefault(key, []).append((row["_from"], row["_to"]))
    reading_times = timestamps
    for row_id, meter_id, machine_id, stamp in zip(readings.row_id, readings.meter_id, readings.machine_id, reading_times):
        if pd.isna(machine_id):
            continue
        windows = assignment_windows.get((str(meter_id), str(machine_id)), [])
        matched = any(pd.notna(start_value) and stamp >= start_value and
                      (pd.isna(end_value) or stamp < end_value)
                      for start_value, end_value in windows)
        if not matched:
            effective_hierarchy_violations.append(str(row_id))

    exceptions = {
        "excluded_readings": excluded_counts,
        "noncanonical_reading_units": sorted(set(readings.loc[readings.unit != CANONICAL_UNIT, "unit"].dropna().astype(str))),
        "effective_dated_hierarchy_violation_count": len(effective_hierarchy_violations),
        "effective_dated_hierarchy_violation_row_ids": effective_hierarchy_violations,
        "meter_register_mismatches": [meter for meter, _, _ in register_mismatches(valid_readings, tables["meter_register_totals"])],
        "tariff_timezone_mismatches": [],
    }
    plant_tariffs = tables["tariffs"][tables["tariffs"].plant_id.astype(str) == str(tables["plants"].plant_id.iloc[0])]
    exceptions["tariff_timezone_mismatches"] = tariff_mismatches(plant_tariffs, plant_timezone).tariff_id.astype(str).tolist()

    return {
        "valid": not errors,
        "errors": errors,
        "exceptions": exceptions,
        "counts": {name: int(len(frame)) for name, frame in tables.items()},
        "validation_scope": "Structural rules are errors; labeled source-quality anomalies are reported separately as exceptions.",
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate(args.data_dir)
    rendered = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered)
