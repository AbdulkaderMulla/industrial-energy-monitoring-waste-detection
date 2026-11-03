from pathlib import Path

import numpy as np
import pandas as pd

from app.services.rules import (
    EXCLUSION_DUPLICATE, EXCLUSION_HIERARCHY, EXCLUSION_UNIT, FINDING_SEVERITY,
    HIGH_IDLE_FACTOR, IDLE_SAVINGS_RATE, INTENSITY_RATIO_THRESHOLD,
    INTENSITY_WINDOW_DAYS, clean_readings, priced_cost, register_mismatches,
    tariff_mismatches,
)

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"

TABLES = [
    "plants",
    "energy_readings",
    "machines",
    "meters",
    "meter_machine",
    "production_batches",
    "batch_machine",
    "tariffs",
    "weather_observations",
    "meter_register_totals",
    "shifts",
    "maintenance_events",
    "state_events",
    "maintenance_events",
"state_events",
]



def load_data(data_dir=None):
    data_dir = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    return {name: pd.read_csv(data_dir / f"{name}.csv") for name in TABLES}


def plant_timezone(data):
    plants = data.get("plants")
    if plants is None or plants.empty:
        return "UTC"
    return str(plants["timezone"].iloc[0])


def _finding(issue_type, evidence, entity_ids):
    return {
        "issue_type": issue_type,
        "severity": FINDING_SEVERITY[issue_type],
        "count": len(entity_ids),
        "evidence": evidence,
        "entity_ids": [str(e) for e in entity_ids],
    }


def _records(frame):
    """DataFrame -> JSON-safe records (NaN becomes None)."""
    return frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")


def calculate_energy_metrics(data):
    valid, excluded = clean_readings(data["energy_readings"], data["meter_machine"])
    tz = plant_timezone(data)
    cost = priced_cost(valid, data["tariffs"], tz)
    priced = cost.notna()
    frame = valid.assign(cost_inr=cost, idle_kwh=valid["energy_kwh"].where(valid["state"] == "IDLE", 0.0))

    total_kwh = float(valid["energy_kwh"].sum())
    idle_kwh = float(frame["idle_kwh"].sum())
    output = int(data["production_batches"]["actual_output_units"].sum())

    by_machine = frame.groupby("machine_id", as_index=False).agg(
        energy_kwh=("energy_kwh", "sum"), cost_inr=("cost_inr", "sum"), idle_kwh=("idle_kwh", "sum"))
    by_machine = by_machine.merge(data["machines"][["machine_id", "machine_name", "rated_power_kw"]], on="machine_id", how="left")
    machine_output = data["batch_machine"].groupby("machine_id", as_index=False).agg(machine_output_units=("output_units", "sum"))
    by_machine = by_machine.merge(machine_output, on="machine_id", how="left")
    by_machine["energy_intensity_kwh_per_unit"] = by_machine["energy_kwh"] / by_machine["machine_output_units"].replace(0, np.nan)

    by_shift = frame.groupby("shift_id", as_index=False).agg(energy_kwh=("energy_kwh", "sum"), idle_kwh=("idle_kwh", "sum")) if "shift_id" in frame else pd.DataFrame()

    return {
        "total_energy_kwh": total_kwh,
        "priced_energy_kwh": float(valid.loc[priced, "energy_kwh"].sum()),
        "unpriced_energy_kwh": float(valid.loc[~priced, "energy_kwh"].sum()),
        "total_cost_inr": float(frame["cost_inr"].sum()),
        "peak_demand_kw": float(valid["avg_power_kw"].max()) if len(valid) else 0.0,
        "average_demand_kw": float(valid["avg_power_kw"].mean()) if len(valid) else 0.0,
        "idle_energy_kwh": idle_kwh,
        "idle_energy_pct": idle_kwh / total_kwh * 100 if total_kwh else 0.0,
        "production_output_units": output,
        "energy_intensity_kwh_per_unit": total_kwh / output if output > 0 else None,
        "excluded_rows": {reason: int(n) for reason, n in excluded["exclusion_reason"].value_counts().items()},
        "machine_summary": _records(by_machine.sort_values("energy_kwh", ascending=False)),
        "energy_by_shift": _records(by_shift) if len(by_shift) else [],
    }


def _high_idle_findings(valid, machines):
    merged = valid.merge(machines[["machine_id", "rated_power_kw"]], on="machine_id", how="left")
    hot = merged[(merged["state"] == "IDLE") & (merged["avg_power_kw"] > merged["rated_power_kw"] * HIGH_IDLE_FACTOR)]
    keys = sorted(set(hot["machine_id"] + "|" + hot["timestamp_utc"].str[:10]))
    if not keys:
        return []
    return [_finding("HIGH_IDLE_CONSUMPTION", f"{len(keys)} machine-day(s) with idle demand above 30% of rated power", keys)]


def _batch_energy(valid, data):
    """Energy stamped inside each batch window on its assigned machine, paired with batch output."""
    readings = valid.assign(_ts=pd.to_datetime(valid["timestamp_utc"], utc=True).dt.tz_localize(None))
    batches = data["production_batches"].merge(data["batch_machine"], on="batch_id", how="inner")
    batches = batches.assign(
        _start=pd.to_datetime(batches["start_utc"], utc=True).dt.tz_localize(None),
        _end=pd.to_datetime(batches["end_utc"], utc=True).dt.tz_localize(None),
    )
    parts = []
    for machine_id, rows in readings.groupby("machine_id"):
        rows = rows.sort_values("_ts")
        cumulative = np.concatenate([[0.0], np.cumsum(rows["energy_kwh"].to_numpy())])
        times = rows["_ts"].to_numpy()
        mb = batches[batches["machine_id"] == machine_id]
        if mb.empty:
            continue
        lo = np.searchsorted(times, mb["_start"].to_numpy(), side="left")
        hi = np.searchsorted(times, mb["_end"].to_numpy(), side="left")
        parts.append(pd.DataFrame({
            "machine_id": machine_id,
            "start": mb["_start"].to_numpy(),
            "energy_kwh": cumulative[hi] - cumulative[lo],
            "output_units": mb["output_units"].to_numpy(),
        }))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _intensity_findings(valid, data):
    """Compare kWh per output unit (batch-window energy / batch output) in the first and last window."""
    if valid.empty:
        return []
    ts = pd.to_datetime(valid["timestamp_utc"], utc=True).dt.tz_localize(None)
    first, last = ts.min(), ts.max()
    window = pd.Timedelta(days=INTENSITY_WINDOW_DAYS)
    if last - first < 2 * window:
        return []
    be = _batch_energy(valid, data)
    if be.empty:
        return []
    early = be[be["start"] < first + window].groupby("machine_id")[["energy_kwh", "output_units"]].sum()
    late = be[be["start"] >= last - window].groupby("machine_id")[["energy_kwh", "output_units"]].sum()
    joined = early.join(late, lsuffix="_early", rsuffix="_late", how="inner")
    joined = joined[(joined.output_units_early > 0) & (joined.output_units_late > 0) & (joined.energy_kwh_early > 0)]
    if joined.empty:
        return []
    ratio = (joined.energy_kwh_late / joined.output_units_late) / (joined.energy_kwh_early / joined.output_units_early)
    flagged = [m for m, r in ratio.items() if np.isfinite(r) and r >= INTENSITY_RATIO_THRESHOLD]
    if not flagged:
        return []
    return [_finding("ENERGY_INTENSITY_SHIFT",
                     f"kWh per output unit rose by at least {INTENSITY_RATIO_THRESHOLD:.2f}x between the first and last {INTENSITY_WINDOW_DAYS} days of batches",
                     sorted(flagged))]


def detect_anomalies(data):
    """Rule-based detection. Reads source fields only; never reads ground-truth labels."""
    findings = []
    valid, excluded = clean_readings(data["energy_readings"], data["meter_machine"])
    tz = plant_timezone(data)

    for reason, label in [
        (EXCLUSION_DUPLICATE, "Repeated reading_id values; later occurrences excluded"),
        (EXCLUSION_UNIT, "Interval row declares a unit other than kWh_interval"),
        (EXCLUSION_HIERARCHY, "Reading references a machine not assigned to its meter"),
    ]:
        rows = excluded[excluded["exclusion_reason"] == reason]
        if len(rows):
            findings.append(_finding(reason, label, rows["row_id"].tolist()))

    mismatches = register_mismatches(valid, data["meter_register_totals"])
    if mismatches:
        findings.append(_finding("METER_TOTAL_MISMATCH",
                                 "; ".join(f"{m}: register={r:.3f} kWh, valid intervals={s:.3f} kWh" for m, r, s in mismatches),
                                 [m for m, _, _ in mismatches]))

    bad_tariffs = tariff_mismatches(data["tariffs"], tz)
    if len(bad_tariffs):
        findings.append(_finding("TARIFF_TIMEZONE_MISMATCH",
                                 f"Tariff timezone differs from plant timezone {tz}",
                                 bad_tariffs["tariff_id"].tolist()))

    findings.extend(_high_idle_findings(valid, data["machines"]))
    findings.extend(_intensity_findings(valid, data))
    return findings


def build_recommendations(data):
    valid, _ = clean_readings(data["energy_readings"], data["meter_machine"])
    cost = priced_cost(valid, data["tariffs"], plant_timezone(data))
    idle = valid.assign(cost_inr=cost)[valid["state"] == "IDLE"]
    per_machine = idle.groupby("machine_id").agg(kwh=("energy_kwh", "sum"), cost=("cost_inr", "sum"))
    recommendations = []
    for _, row in data["machines"].iterrows():
        if row.machine_id not in per_machine.index:
            continue
        baseline_kwh = float(per_machine.loc[row.machine_id, "kwh"])
        baseline_cost = float(per_machine.loc[row.machine_id, "cost"])
        savings_kwh = baseline_kwh * IDLE_SAVINGS_RATE
        if savings_kwh <= 0.01:
            continue
        recommendations.append({
            "recommendation_id": f"REC-2026-{len(recommendations)+1:06d}",
            "machine_id": row.machine_id,
            "reason": "Review idle shutdown policy; estimated avoidable idle energy is 25% of observed valid idle energy.",
            "baseline_kwh": baseline_kwh,
            "baseline_priced_cost_inr": baseline_cost,
            "expected_savings_kwh": savings_kwh,
            "expected_savings_inr": baseline_cost * IDLE_SAVINGS_RATE,
            "priority": "HIGH" if baseline_kwh > 100 else "MEDIUM",
            "status": "OPEN",
        })
    return recommendations


# --------------------------------------------------
# PRODUCTION EFFICIENCY ANALYSIS
# --------------------------------------------------

# PRODUCTION EFFICIENCY ANALYSIS
# --------------------------------------------------

def analyze_production_efficiency(data):
    """Allocate machine energy readings to production batches."""

    readings, _ = clean_readings(data["energy_readings"], data["meter_machine"])
    readings = readings.copy()

    readings["interval_end"] = pd.to_datetime(
        readings["timestamp_utc"], utc=True, errors="coerce"
    )

    readings = readings.dropna(subset=["interval_end"])

    readings["interval_start"] = (
        readings["interval_end"] - pd.Timedelta(minutes=15)
    )

    readings["energy_kwh"] = pd.to_numeric(
        readings["energy_kwh"], errors="coerce"
    ).fillna(0)

    batches = data["production_batches"].copy()
    bridge = data["batch_machine"].copy()

    batches["start"] = pd.to_datetime(
        batches["start_utc"], utc=True, errors="coerce"
    )

    batches["end"] = pd.to_datetime(
        batches["end_utc"], utc=True, errors="coerce"
    )

    batches = batches.merge(
        bridge[["batch_id", "machine_id", "output_units"]],
        on="batch_id",
        how="left"
    )

    batches = batches.merge(
        data["machines"][["machine_id", "machine_name"]],
        on="machine_id",
        how="left"
    )

    details = []

    for _, batch in batches.iterrows():

        if (
            pd.isna(batch["machine_id"])
            or pd.isna(batch["start"])
            or pd.isna(batch["end"])
            or batch["end"] <= batch["start"]
        ):
            continue

        machine_readings = readings[
            readings["machine_id"] == batch["machine_id"]
        ].copy()

        allocated_energy = 0.0

        if not machine_readings.empty:

            overlap_start = machine_readings["interval_start"].clip(
                lower=batch["start"]
            )

            overlap_end = machine_readings["interval_end"].clip(
                upper=batch["end"]
            )

            overlap_minutes = (
                overlap_end - overlap_start
            ).dt.total_seconds().clip(lower=0) / 60

            fractions = (overlap_minutes / 15).clip(upper=1)

            allocated_energy = float(
                (
                    machine_readings["energy_kwh"].to_numpy()
                    * fractions.to_numpy()
                ).sum()
            )

        output = (
            float(batch["output_units"])
            if pd.notna(batch["output_units"])
            else float(batch["actual_output_units"])
        )

        planned = float(batch["planned_output_units"])

        details.append({
            "batch_id": batch["batch_id"],
            "machine_id": batch["machine_id"],
            "machine_name": batch["machine_name"],
            "start_utc": batch["start_utc"],
            "end_utc": batch["end_utc"],
            "actual_output_units": output,
            "planned_output_units": planned,
            "output_attainment_pct": (
                output / planned * 100 if planned > 0 else None
            ),
            "allocated_energy_kwh": allocated_energy,
            "energy_kwh_per_unit": (
                allocated_energy / output if output > 0 else None
            ),
            "status": batch["status"]
        })

    detail = pd.DataFrame(details)

    if detail.empty:
        return {
            "batch_detail": [],
            "machine_summary": [],
            "overall_intensity": None
        }

    machine_summary = detail.groupby(
        ["machine_id", "machine_name"],
        as_index=False
    ).agg(
        batches=("batch_id", "count"),
        output_units=("actual_output_units", "sum"),
        allocated_energy_kwh=("allocated_energy_kwh", "sum"),
        planned_units=("planned_output_units", "sum")
    )

    machine_summary["energy_kwh_per_unit"] = (
        machine_summary["allocated_energy_kwh"]
        / machine_summary["output_units"].replace(0, np.nan)
    )

    machine_summary["output_attainment_pct"] = (
        machine_summary["output_units"]
        / machine_summary["planned_units"].replace(0, np.nan)
        * 100
    )

    total_output = float(detail["actual_output_units"].sum())
    total_energy = float(detail["allocated_energy_kwh"].sum())

    return {
        "batch_detail": detail.sort_values(
            "start_utc"
        ).to_dict(orient="records"),

        "machine_summary": machine_summary.sort_values(
            "energy_kwh_per_unit",
            ascending=False
        ).to_dict(orient="records"),

        "overall_intensity": (
            total_energy / total_output if total_output > 0 else None
        )
    }


def analyze_weather_energy(data, bucket_hours=6):
    """Join weather to energy and batch output in matching UTC time buckets.

    The resulting correlations are descriptive summaries, not causal estimates.
    Batch output is prorated across every bucket the batch overlaps.
    """
    if bucket_hours <= 0 or 24 % bucket_hours:
        raise ValueError("bucket_hours must be a positive divisor of 24")

    weather = data.get("weather_observations", pd.DataFrame()).copy()
    if weather.empty:
        return {"bucket_hours": bucket_hours, "observations": [], "correlations": {}, "note": "No weather observations available."}

    weather["timestamp_utc"] = pd.to_datetime(weather["timestamp_utc"], utc=True, errors="coerce")
    weather = weather.dropna(subset=["timestamp_utc"])
    weather["bucket_utc"] = weather["timestamp_utc"].dt.floor(f"{bucket_hours}h")

    valid, _ = clean_readings(data["energy_readings"], data["meter_machine"])
    meters = data["meters"][["meter_id", "plant_id"]].drop_duplicates("meter_id")
    valid = valid.merge(meters, on="meter_id", how="left")
    valid["timestamp_utc"] = pd.to_datetime(valid["timestamp_utc"], utc=True, errors="coerce")
    valid = valid.dropna(subset=["timestamp_utc", "plant_id"])
    valid["bucket_utc"] = valid["timestamp_utc"].dt.floor(f"{bucket_hours}h")
    valid["idle_kwh"] = valid["energy_kwh"].where(valid["state"] == "IDLE", 0.0)
    energy = valid.groupby(["plant_id", "bucket_utc"], as_index=False).agg(
        energy_kwh=("energy_kwh", "sum"),
        average_demand_kw=("avg_power_kw", "mean"),
        peak_demand_kw=("avg_power_kw", "max"),
        idle_energy_kwh=("idle_kwh", "sum"),
    )

    batches = data["production_batches"].merge(
    data["batch_machine"],
    on="batch_id",
    how="inner"
)

    batch_output = {}
    for row in batches.itertuples(index=False):
        start = pd.to_datetime(row.start_utc, utc=True, errors="coerce")
        end = pd.to_datetime(row.end_utc, utc=True, errors="coerce")
        if pd.isna(start) or pd.isna(end) or end <= start or pd.isna(row.plant_id):
            continue
        duration = (end - start).total_seconds()
        cursor = start.floor(f"{bucket_hours}h")
        while cursor < end:
            bucket_end = cursor + pd.Timedelta(hours=bucket_hours)
            overlap = max(0.0, (min(end, bucket_end) - max(start, cursor)).total_seconds())
            if overlap:
                key = (row.plant_id, cursor)
                batch_output[key] = batch_output.get(key, 0.0) + float(row.output_units) * overlap / duration
            cursor = bucket_end
    output = pd.DataFrame(
        [{"plant_id": plant_id, "bucket_utc": bucket, "production_output_units": units}
         for (plant_id, bucket), units in batch_output.items()],
        columns=["plant_id", "bucket_utc", "production_output_units"],
    )

    joined = weather.merge(energy, on=["plant_id", "bucket_utc"], how="left")
    joined = joined.merge(output, on=["plant_id", "bucket_utc"], how="left")
    for column in ["energy_kwh", "average_demand_kw", "peak_demand_kw", "idle_energy_kwh", "production_output_units"]:
        joined[column] = joined[column].fillna(0.0)
    joined["energy_intensity_kwh_per_unit"] = joined["energy_kwh"].div(
        joined["production_output_units"].where(joined["production_output_units"] > 0)
    )

    metrics = ["energy_kwh", "average_demand_kw", "peak_demand_kw", "idle_energy_kwh",
               "production_output_units", "energy_intensity_kwh_per_unit"]
    correlations = {}
    for weather_field in ["temperature_c", "humidity_pct"]:
        correlations[weather_field] = {}
        for metric in metrics:
            pair = joined[[weather_field, metric]].dropna()
            coefficient = None
            if len(pair) >= 3 and pair[weather_field].nunique() > 1 and pair[metric].nunique() > 1:
                coefficient = float(pair[weather_field].corr(pair[metric]))
            correlations[weather_field][metric] = {
                "pearson_r": coefficient,
                "sample_count": int(len(pair)),
            }

    result = joined.sort_values(["timestamp_utc", "plant_id"]).copy()
    result["timestamp_utc"] = result["timestamp_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    result["bucket_utc"] = result["bucket_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    result = result.drop(columns=["plant_id"])
    return {
        "bucket_hours": bucket_hours,
        "observations": _records(result),
        "correlations": correlations,
        "note": "Pearson correlations join each weather observation to matching UTC energy and production buckets. They describe association and do not establish causation.",
    }
