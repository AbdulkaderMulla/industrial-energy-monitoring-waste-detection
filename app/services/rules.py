"""Documented business rules shared by the generator, validation and analytics.

Detection code reads only source fields. Injected-defect labels live in
data/ground_truth/ and are never imported by the app.
"""
import pandas as pd

CANONICAL_UNIT = "kWh_interval"
INTERVAL_HOURS = 0.25
RUNNING_STATES = {"RUNNING", "IDLE", "MAINTENANCE"}

# Exclusion rules, applied in this order to readings that are still valid.
EXCLUSION_UNIT = "UNIT_KW_KWH_CONFUSION"
EXCLUSION_DUPLICATE = "DUPLICATE_READING"
EXCLUSION_HIERARCHY = "METER_MACHINE_HIERARCHY_VIOLATION"

# Detection thresholds.
REGISTER_TOLERANCE_KWH = 0.01
REGISTER_TOLERANCE_PCT = 0.001
HIGH_IDLE_FACTOR = 0.30
INTENSITY_WINDOW_DAYS = 30
INTENSITY_RATIO_THRESHOLD = 1.20
IDLE_SAVINGS_RATE = 0.25

FINDING_SEVERITY = {
    EXCLUSION_DUPLICATE: "MEDIUM",
    EXCLUSION_UNIT: "HIGH",
    EXCLUSION_HIERARCHY: "HIGH",
    "METER_TOTAL_MISMATCH": "HIGH",
    "TARIFF_TIMEZONE_MISMATCH": "MEDIUM",
    "HIGH_IDLE_CONSUMPTION": "MEDIUM",
    "ENERGY_INTENSITY_SHIFT": "MEDIUM",
}


def classify_readings(readings, meter_machine):
    """Return an exclusion reason per reading ('' means valid)."""
    reason = pd.Series("", index=readings.index, dtype=object)
    reason.loc[readings["unit"] != CANONICAL_UNIT] = EXCLUSION_UNIT

    candidates = reason == ""
    dup = readings.loc[candidates, "reading_id"].duplicated(keep="first")
    reason.loc[dup[dup].index] = EXCLUSION_DUPLICATE

    pairs = set(zip(meter_machine["meter_id"], meter_machine["machine_id"]))
    candidates = reason == ""
    mapped = pd.Series(
        [pd.isna(c) or (m, c) in pairs for m, c in zip(readings["meter_id"], readings["machine_id"])],
        index=readings.index,
    )
    reason.loc[candidates & ~mapped] = EXCLUSION_HIERARCHY
    return reason


def clean_readings(readings, meter_machine):
    """Split readings into (valid, excluded). Excluded rows carry exclusion_reason."""
    reason = classify_readings(readings, meter_machine)
    valid = readings.loc[reason == ""].copy()
    excluded = readings.loc[reason != ""].copy()
    excluded["exclusion_reason"] = reason[reason != ""]
    return valid, excluded


def register_mismatches(valid, totals):
    """Meters whose register total differs from the sum of valid intervals."""
    if totals is None or len(totals) == 0:
        return []
    sums = valid.groupby("meter_id")["energy_kwh"].sum()
    found = []
    for _, row in totals.iterrows():
        summed = float(sums.get(row["meter_id"], 0.0))
        register = float(row["register_total_kwh"])
        tolerance = max(REGISTER_TOLERANCE_KWH, REGISTER_TOLERANCE_PCT * abs(summed))
        if abs(register - summed) > tolerance:
            found.append((row["meter_id"], register, summed))
    return found


def tariff_mismatches(tariffs, plant_timezone):
    return tariffs.loc[tariffs["timezone"] != plant_timezone]


def priced_cost(valid, tariffs, plant_timezone):
    """Per-reading cost in INR; NaN where no effective, matching tariff covers it."""
    timestamps = pd.to_datetime(valid["timestamp_utc"], utc=True, errors="coerce")
    rates = pd.Series(float("nan"), index=valid.index, dtype=float)
    matching = tariffs.loc[tariffs["timezone"] == plant_timezone]
    for tariff in matching.itertuples(index=False):
        effective_from = pd.to_datetime(tariff.effective_from, utc=True, errors="coerce")
        effective_to = pd.to_datetime(getattr(tariff, "effective_to", None), utc=True, errors="coerce")
        in_effect = timestamps.ge(effective_from)
        if pd.notna(effective_to):
            in_effect &= timestamps.lt(effective_to)
        in_window = timestamps.dt.hour.ge(int(tariff.start_hour_utc)) & timestamps.dt.hour.lt(int(tariff.end_hour_utc))
        applies = in_effect & in_window & rates.isna()
        rates.loc[applies] = float(tariff.rate_inr_per_kwh)
    rate = rates
    return (valid["energy_kwh"] * rate).astype(float)
