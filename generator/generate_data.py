"""Deterministic synthetic generator for the industrial energy monitoring project.

Source tables in <output>/raw contain NO labels. Injected defects and rule-derived
waste labels are written only to <output>/ground_truth/ground_truth.csv.
"""
import argparse
import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app.services.rules import (
    CANONICAL_UNIT, HIGH_IDLE_FACTOR, IDLE_SAVINGS_RATE, INTERVAL_HOURS,
    priced_cost,
)

PLANT_ID = "PLANT-001"
PLANT_TIMEZONE = "UTC"
SEED_DEFAULT = 20261022
PROFILES = {"starter": (3, 7, 40), "full": (20, 90, 2000)}  # meters, days, batches
INTENSITY_SHIFT_FACTOR = 1.35
KWH_PER_OUTPUT_UNIT = 0.05
INTENSITY_SHIFT_START_FRACTION = 2 / 3

# label type -> (documented rule, expected decision)
LABEL_RULES = {
    "METER_TOTAL_MISMATCH": ("register total differs from sum of valid intervals beyond tolerance", "HOLD_METER_FOR_RECONCILIATION"),
    "UNIT_KW_KWH_CONFUSION": ("interval row declares a unit other than kWh_interval", "EXCLUDE_ROW_AND_REVIEW_UNIT"),
    "TARIFF_TIMEZONE_MISMATCH": ("tariff timezone differs from plant timezone", "CORRECT_TARIFF_TIMEZONE"),
    "DUPLICATE_READING": ("repeated reading_id; first occurrence is authoritative", "EXCLUDE_DUPLICATE_ROW"),
    "METER_MACHINE_HIERARCHY_VIOLATION": ("machine is not assigned to the reading's meter", "EXCLUDE_UNMAPPED_ROW"),
    "HIGH_IDLE_CONSUMPTION": ("IDLE interval with avg_power_kw above 30% of rated power", "REVIEW_IDLE_SHUTDOWN_POLICY"),
    "ENERGY_INTENSITY_SHIFT": ("kWh per output in last 30 days at least 1.20x the first 30 days", "INVESTIGATE_PROCESS_CHANGE"),
}


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def write_csv(df, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def build(profile="starter", seed=SEED_DEFAULT, output=Path("data")):
    if profile not in PROFILES:
        raise ValueError(f"unknown profile: {profile}")
    meter_count, days, batch_count = PROFILES[profile]
    output = Path(output)
    rng = np.random.default_rng(seed)
    py_rng = random.Random(seed)

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    timestamps = [start + timedelta(minutes=15 * i) for i in range(days * 96)]
    shift_days_start = int(days * INTENSITY_SHIFT_START_FRACTION)

    plants = pd.DataFrame([{"plant_id": PLANT_ID, "name": "Synthetic Plant Alpha", "location": "Synthetic site",
                            "timezone": PLANT_TIMEZONE, "status": "ACTIVE"}])
    shifts = [
        {"shift_id": "SH-001", "plant_id": PLANT_ID, "shift_name": "DAY", "start_time": "06:00", "end_time": "14:00", "effective_from": iso(start), "effective_to": ""},
        {"shift_id": "SH-002", "plant_id": PLANT_ID, "shift_name": "EVENING", "start_time": "14:00", "end_time": "22:00", "effective_from": iso(start), "effective_to": ""},
        {"shift_id": "SH-003", "plant_id": PLANT_ID, "shift_name": "NIGHT", "start_time": "22:00", "end_time": "06:00", "effective_from": iso(start), "effective_to": ""},
    ]
    shift_windows = [(s["shift_id"], int(s["start_time"][:2]), int(s["end_time"][:2])) for s in shifts]

    def shift_for(ts):
        h = ts.hour
        for sid, a, b in shift_windows:
            if (a <= h < b) if a < b else (h >= a or h < b):
                return sid
        raise AssertionError("shift calendar does not cover every hour")

    tariffs = [
        {"tariff_id": "TAR-2026-001", "plant_id": PLANT_ID, "tariff_name": "OFF_PEAK", "start_hour_utc": 0, "end_hour_utc": 6, "rate_inr_per_kwh": 5.0, "effective_from": iso(start), "effective_to": "", "timezone": PLANT_TIMEZONE},
        {"tariff_id": "TAR-2026-002", "plant_id": PLANT_ID, "tariff_name": "NORMAL", "start_hour_utc": 6, "end_hour_utc": 18, "rate_inr_per_kwh": 7.0, "effective_from": iso(start), "effective_to": "", "timezone": PLANT_TIMEZONE},
        {"tariff_id": "TAR-2026-003", "plant_id": PLANT_ID, "tariff_name": "PEAK", "start_hour_utc": 18, "end_hour_utc": 24, "rate_inr_per_kwh": 11.0, "effective_from": iso(start), "effective_to": "", "timezone": PLANT_TIMEZONE},
    ]

    machines, meters, assignments = [], [], []
    for i in range(meter_count):
        machine_id = f"MCH-{i+1:03d}"
        meter_id = f"MTR-{PLANT_ID}-{i+1:03d}"
        machines.append({"machine_id": machine_id, "plant_id": PLANT_ID, "machine_name": f"Production Machine {i+1:02d}",
                         "machine_type": ["CNC", "COMPRESSOR", "PUMP", "CONVEYOR"][i % 4],
                         "rated_power_kw": round(float(rng.uniform(12, 55)), 2), "status": "ACTIVE"})
        meters.append({"meter_id": meter_id, "plant_id": PLANT_ID, "meter_name": f"Submeter {i+1:02d}",
                       "unit": CANONICAL_UNIT, "cadence_minutes": 15, "status": "ACTIVE"})
        assignments.append({"assignment_id": f"MM-{i+1:03d}", "meter_id": meter_id, "machine_id": machine_id,
                            "effective_from": iso(start), "effective_to": ""})

    # Maintenance events are generated first so readings can reflect them.
    maint_count = min(10, meter_count * 2)
    maintenance, maint_windows = [], {}
    for i in range(maint_count):
        machine_id = machines[i % meter_count]["machine_id"]
        t = timestamps[int((i + 1) * len(timestamps) / (maint_count + 1))]
        maintenance.append({"event_id": f"MAINT-{i+1:04d}", "machine_id": machine_id, "event_type": "PREVENTIVE_INSPECTION",
                            "start_utc": iso(t), "end_utc": iso(t + timedelta(hours=1)), "status": "COMPLETED",
                            "notes": "Synthetic scheduled maintenance"})
        maint_windows.setdefault(machine_id, []).append((t, t + timedelta(hours=1)))

    shift_machines = {machines[i]["machine_id"] for i in range(meter_count) if i % 5 == 4}

    readings = []
    for mi, meter in enumerate(meters):
        machine = machines[mi]
        rated = machine["rated_power_kw"]
        for ti, ts in enumerate(timestamps):
            hour = ts.hour
            active = 7 <= hour < 22
            idle = (not active) or (ti % 173 in (0, 1, 2))
            in_maint = any(a <= ts < b for a, b in maint_windows.get(machine["machine_id"], []))
            if in_maint:
                state, base_kw = "MAINTENANCE", rated * 0.02
            else:
                state = "IDLE" if idle else "RUNNING"
                factor = INTENSITY_SHIFT_FACTOR if (machine["machine_id"] in shift_machines and not idle and ti >= shift_days_start * 96) else 1.0
                base_kw = rated * (0.13 if idle else 0.48) * factor
            daily_wave = 1 + 0.08 * np.sin(2 * np.pi * (hour / 24))
            noise = float(rng.normal(0, rated * 0.025))
            spike = rated * 0.75 if (ti + mi * 37) % 997 == 0 else 0
            avg_kw = max(0.2, base_kw * daily_wave + noise + spike)
            energy = avg_kw * INTERVAL_HOURS
            if (ti + mi * 19) % 1201 == 0:  # deterministic meter gap
                continue
            reading_id = f"ENG-{meter['meter_id']}-{ts.strftime('%Y%m%dT%H%MZ')}"
            readings.append({"row_id": reading_id, "reading_id": reading_id, "meter_id": meter["meter_id"],
                             "machine_id": machine["machine_id"], "shift_id": shift_for(ts),
                             "timestamp_utc": iso(ts), "energy_kwh": round(energy, 5), "avg_power_kw": round(avg_kw, 5),
                             "unit": CANONICAL_UNIT, "state": state})
    readings_df = pd.DataFrame(readings)
    machines_df = pd.DataFrame(machines)
    meters_df = pd.DataFrame(meters)
    assignments_df = pd.DataFrame(assignments)

    # Production batches (shift from batch start).
    rated_map_gen = {m["machine_id"]: m["rated_power_kw"] for m in machines}
    # Batches run inside productive hours; output is proportional to the energy the batch
    # would draw at the machine's running rate, so kWh per output unit is a meaningful metric.
    productive = [i for i, ts in enumerate(timestamps) if 7 <= ts.hour < 19]
    batches, batch_machine = [], []
    for bi in range(batch_count):
        machine_idx = bi % meter_count
        # Scheduled cadence: each machine's batches are spread evenly over the period, with jitter.
        k, per_machine = bi // meter_count, len(range(machine_idx, batch_count, meter_count))
        slot = int((k + 0.5) * len(productive) / per_machine)
        jitter = int(rng.integers(-8, 9))
        offset = productive[min(max(slot + jitter, 0), len(productive) - 1)]
        batch_start = timestamps[offset]
        duration = int(rng.integers(1, 9))
        batch_end = batch_start + timedelta(minutes=15 * duration)
        expected_kwh = duration * INTERVAL_HOURS * rated_map_gen[machines[machine_idx]["machine_id"]] * 0.48
        output_units = max(1, int(round(expected_kwh / KWH_PER_OUTPUT_UNIT * float(rng.uniform(0.9, 1.1)))))
        batch_id = f"BATCH-2026-{bi+1:06d}"
        batches.append({"batch_id": batch_id, "plant_id": PLANT_ID, "shift_id": shift_for(batch_start),
                        "start_utc": iso(batch_start), "end_utc": iso(batch_end),
                        "planned_output_units": int(output_units * 1.05), "actual_output_units": output_units,
                        "status": "COMPLETED"})
        batch_machine.append({"batch_machine_id": f"BM-{bi+1:06d}", "batch_id": batch_id,
                              "machine_id": machines[machine_idx]["machine_id"], "output_units": output_units})

    # Weather every 6 hours with a diurnal cycle.
    weather = []
    for day in range(days):
        for slot in range(4):
            ts = start + timedelta(days=day, hours=6 * slot)
            temp = 25 + 7 * np.sin(day / 9) + 3 * np.sin(2 * np.pi * (ts.hour - 14) / 24) + rng.normal(0, 1.0)
            weather.append({"weather_id": f"WTH-{len(weather)+1:05d}", "plant_id": PLANT_ID,
                            "timestamp_utc": iso(ts), "temperature_c": round(float(temp), 2),
                            "humidity_pct": round(float(np.clip(55 + rng.normal(0, 12), 20, 95)), 2),
                            "condition": py_rng.choice(["CLEAR", "CLOUDY", "RAINY"])})

    state_events = []

    def add_state_event(entity_type, entity_id, old_state, new_state, event_time, reason):
        event_identity = f"{entity_type}|{entity_id}|{iso(event_time)}"
        event_key = hashlib.sha256(event_identity.encode("utf-8")).hexdigest()[:16].upper()
        state_events.append({
            "state_event_id": f"EVT-{event_key}",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "old_state": old_state or "",
            "new_state": new_state,
            "event_utc": iso(event_time),
            "actor": "SYSTEM",
            "reason": reason,
        })

    for machine in machines:
        add_state_event("MACHINE_STATUS", machine["machine_id"], "", "ACTIVE", start,
                        "Initial synthetic master-data lifecycle state")
        machine_readings = readings_df[readings_df.machine_id == machine["machine_id"]].sort_values("timestamp_utc")
        previous_state = ""
        for row in machine_readings.itertuples(index=False):
            if row.state != previous_state:
                add_state_event(
                    "MACHINE_OPERATING_STATE", machine["machine_id"], previous_state, row.state,
                    datetime.fromisoformat(row.timestamp_utc.replace("Z", "+00:00")),
                    "Operational-state transition derived from source telemetry",
                )
                previous_state = row.state

    # ---- Baseline derived values (computed from valid source rows, before any injection) ----
    baseline_tariffs = pd.DataFrame(tariffs)
    rated_map = dict(zip(machines_df.machine_id, machines_df.rated_power_kw))
    priced = readings_df.copy()
    priced["cost_inr"] = priced_cost(priced, baseline_tariffs, PLANT_TIMEZONE)
    idle_rows = priced[priced["state"] == "IDLE"]
    recommendations = []
    for machine in machines:
        mid = machine["machine_id"]
        m_idle = idle_rows[idle_rows.machine_id == mid]
        baseline_kwh = float(m_idle.energy_kwh.sum())
        baseline_cost = float(m_idle.cost_inr.sum())
        savings_kwh = baseline_kwh * IDLE_SAVINGS_RATE
        if savings_kwh <= 0.01:
            continue
        recommendations.append({
            "recommendation_id": f"REC-2026-{len(recommendations)+1:06d}", "machine_id": mid,
            "created_utc": iso(start + timedelta(days=days - 1)),
            "reason": "Review idle shutdown policy; estimate is 25% of observed valid idle energy.",
            "baseline_kwh": round(baseline_kwh, 5), "expected_savings_kwh": round(savings_kwh, 5),
            "expected_savings_inr": round(baseline_cost * IDLE_SAVINGS_RATE, 5),
            "priority": "HIGH" if baseline_kwh > 100 else "MEDIUM", "status": "OPEN"})
    register_totals = [{"meter_id": m["meter_id"],
                        "register_total_kwh": round(float(readings_df.loc[readings_df.meter_id == m["meter_id"], "energy_kwh"].sum()), 5)}
                       for m in meters]

    # ---- Labelled ground truth: rule-derived waste labels on valid source rows ----
    labels = []
    def add_label(issue_type, entity_id, label_source):
        rule, decision = LABEL_RULES[issue_type]
        labels.append({"ground_truth_id": f"GT-{len(labels)+1:04d}", "issue_type": issue_type, "entity_id": entity_id,
                       "expected_detection": True, "expected_decision": decision, "rule": rule,
                       "label_source": label_source})

    idle_hot = idle_rows.copy()
    idle_hot["rated"] = idle_hot.machine_id.map(rated_map)
    idle_hot = idle_hot[idle_hot.avg_power_kw > idle_hot.rated * HIGH_IDLE_FACTOR]
    for key in sorted(set(idle_hot.machine_id + "|" + idle_hot.timestamp_utc.str[:10])):
        add_label("HIGH_IDLE_CONSUMPTION", key, "DOCUMENTED_RULE_ON_SOURCE")

    # ---- Injected defects (labelled, never silently mixed into unrelated rows) ----
    tariff_frame = pd.DataFrame(tariffs)
    tariff_frame.loc[tariff_frame.tariff_id == "TAR-2026-002", "timezone"] = "Asia/Kolkata"
    add_label("TARIFF_TIMEZONE_MISMATCH", "TAR-2026-002", "INJECTED_DEFECT")

    readings_list = readings_df.to_dict(orient="records")
    original_dup = readings_list[5]
    readings_list.append({**original_dup, "row_id": "EXC-DUPLICATE-001"})
    add_label("DUPLICATE_READING", "EXC-DUPLICATE-001", "INJECTED_DEFECT")

    unit_row = {**readings_list[20], "row_id": "EXC-UNIT-001", "reading_id": "EXC-UNIT-001", "unit": "kW"}
    readings_list.append(unit_row)
    add_label("UNIT_KW_KWH_CONFUSION", "EXC-UNIT-001", "INJECTED_DEFECT")

    wrong_machine = machines[-1]["machine_id"]
    host = readings_list[30]
    if wrong_machine != host["machine_id"] and meter_count > 1:
        readings_list.append({**host, "row_id": "EXC-HIERARCHY-001", "reading_id": "EXC-HIERARCHY-001",
                              "machine_id": wrong_machine})
        add_label("METER_MACHINE_HIERARCHY_VIOLATION", "EXC-HIERARCHY-001", "INJECTED_DEFECT")
    else:
        raise AssertionError("hierarchy fixture needs a second meter and an unassigned machine")

    # Meter register mismatch: the register is overstated by 2% on the first meter.
    register_totals[0]["register_total_kwh"] = round(register_totals[0]["register_total_kwh"] * 1.02, 5)
    add_label("METER_TOTAL_MISMATCH", meters[0]["meter_id"], "INJECTED_DEFECT")

    # Energy-intensity shift: labelled machines from the configured shift config.
    for machine in machines:
        if machine["machine_id"] in shift_machines:
            add_label("ENERGY_INTENSITY_SHIFT", machine["machine_id"], "INJECTED_SHIFT_CONFIG")

    readings_out = pd.DataFrame(readings_list)
    readings_out = readings_out.drop(columns=[c for c in ["cost_inr"] if c in readings_out.columns])

    tables = {
        "plants": plants, "meters": meters_df, "machines": machines_df, "meter_machine": assignments_df,
        "energy_readings": readings_out, "production_batches": pd.DataFrame(batches),
        "batch_machine": pd.DataFrame(batch_machine), "shifts": pd.DataFrame(shifts),
        "tariffs": tariff_frame, "weather_observations": pd.DataFrame(weather),
        "maintenance_events": pd.DataFrame(maintenance), "recommendations": pd.DataFrame(recommendations),
        "state_events": pd.DataFrame(state_events), "meter_register_totals": pd.DataFrame(register_totals),
    }
    raw_dir = output / "raw"
    for name, df in tables.items():
        write_csv(df, raw_dir / f"{name}.csv")
    gt_df = pd.DataFrame(labels)
    write_csv(gt_df, output / "ground_truth" / "ground_truth.csv")

    summary = {
        "profile": profile, "seed": seed, "baseline_meter_count": meter_count, "days": days,
        "interval_minutes": 15, "expected_baseline_readings": meter_count * days * 96,
        "energy_reading_rows_including_gaps_and_fixtures": len(readings_out),
        "meter_gap_intervals": meter_count * days * 96 - len(readings_df),
        "production_batches": len(batches), "weather_observations": len(weather),
        "maintenance_events": len(maintenance), "recommendations": len(recommendations),
        "state_events": len(state_events),
        "ground_truth_labels": int(len(gt_df)),
        "ground_truth_by_type": {k: int(v) for k, v in gt_df.issue_type.value_counts().sort_index().items()},
        "injected_defects": int((gt_df.label_source != "DOCUMENTED_RULE_ON_SOURCE").sum()) if len(gt_df) else 0,
        "source": "synthetic; no external data",
    }
    (output / "processed").mkdir(parents=True, exist_ok=True)
    (output / "processed" / "generation_summary.json").write_text(json.dumps(summary, indent=2))
    # Save a machine-readable validation report beside the generated profile.
    from validation.validate_data import validate
    validation_summary = validate(raw_dir)
    (output / "processed" / "validation_summary.json").write_text(json.dumps(validation_summary, indent=2))
    hashes = {}
    for p in sorted(list(raw_dir.glob("*.csv")) + [output / "ground_truth" / "ground_truth.csv"]):
        hashes[str(p.relative_to(output))] = hashlib.sha256(p.read_bytes()).hexdigest()
    (output / "processed" / "reproducibility.json").write_text(json.dumps({"seed": seed, "profile": profile, "sha256": hashes}, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=sorted(PROFILES), default="starter")
    parser.add_argument("--seed", type=int, default=SEED_DEFAULT)
    parser.add_argument("--output", type=Path, default=Path("data"))
    args = parser.parse_args()
    print(json.dumps(build(args.profile, args.seed, args.output), indent=2))


if __name__ == "__main__":
    main()
