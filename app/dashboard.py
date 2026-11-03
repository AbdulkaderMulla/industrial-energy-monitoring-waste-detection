"""Role-oriented dashboard perspectives for synthetic plant energy monitoring."""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from app.services.analytics import (
    analyze_production_efficiency,
    analyze_weather_energy,
    build_recommendations,
    calculate_energy_metrics,
    detect_anomalies,
    load_data,
)
from app.services.rules import clean_readings
from validation.validate_data import validate

st.set_page_config(page_title="Industrial Energy Monitor", page_icon="⚡", layout="wide")
st.title("⚡ Industrial Energy Monitoring & Waste Detection")
st.caption("Synthetic plant data • 15-minute telemetry • UTC tariff and weather windows")
st.info("Dashboard tabs organize the work by plant role. They are workflow perspectives, not authenticated access controls.")


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


try:
    raw_data = load_data(PROJECT_ROOT / "data" / "raw")
except FileNotFoundError:
    st.error("Dataset not found. Run: `python -m generator.generate_data --profile starter`")
    st.stop()

readings_all = raw_data["energy_readings"].copy()
readings_all["timestamp_utc"] = pd.to_datetime(readings_all["timestamp_utc"], utc=True, errors="coerce")
valid_dates = readings_all["timestamp_utc"].dropna()
if valid_dates.empty:
    st.error("No valid energy-reading timestamps were found.")
    st.stop()
min_date, max_date = valid_dates.min().date(), valid_dates.max().date()

st.sidebar.header("Data filters")
date_range = st.sidebar.date_input("Date range (UTC)", value=(min_date, max_date), min_value=min_date, max_value=max_date)
if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date = end_date = date_range

machine_options = raw_data["machines"]["machine_id"].dropna().astype(str).tolist()
machine_labels = dict(zip(raw_data["machines"]["machine_id"], raw_data["machines"]["machine_name"]))
selected_machines = st.sidebar.multiselect(
    "Machines", machine_options, default=machine_options,
    format_func=lambda machine_id: f"{machine_labels.get(machine_id, machine_id)} ({machine_id})",
)
severity_options = ["HIGH", "MEDIUM", "LOW"]
selected_severities = st.sidebar.multiselect("Finding severity", severity_options, default=severity_options)

start_ts = pd.Timestamp(start_date, tz="UTC")
end_ts = pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(days=1)
data = {key: value.copy() if isinstance(value, pd.DataFrame) else value for key, value in raw_data.items()}
readings = data["energy_readings"]
readings["_ts"] = pd.to_datetime(readings["timestamp_utc"], utc=True, errors="coerce")
data["energy_readings"] = readings[
    readings["_ts"].ge(start_ts) & readings["_ts"].lt(end_ts)
    & readings["machine_id"].astype(str).isin(selected_machines)
].drop(columns="_ts")
data["machines"] = data["machines"][data["machines"]["machine_id"].astype(str).isin(selected_machines)]
data["meter_machine"] = data["meter_machine"][data["meter_machine"]["machine_id"].astype(str).isin(selected_machines)]
data["batch_machine"] = data["batch_machine"][data["batch_machine"]["machine_id"].astype(str).isin(selected_machines)]
maintenance = data["maintenance_events"].copy()
maintenance["_start"] = pd.to_datetime(maintenance["start_utc"], utc=True, errors="coerce")
maintenance["_end"] = pd.to_datetime(maintenance["end_utc"], utc=True, errors="coerce")
maintenance_overlap = maintenance["_start"].lt(end_ts) & (maintenance["_end"].isna() | maintenance["_end"].ge(start_ts))
data["maintenance_events"] = maintenance[
    maintenance["machine_id"].astype(str).isin(selected_machines) & maintenance_overlap
].drop(columns=["_start", "_end"])
state_events = data["state_events"].copy()
state_events["_event_ts"] = pd.to_datetime(state_events["event_utc"], utc=True, errors="coerce")
data["state_events"] = state_events[
    state_events["entity_id"].astype(str).isin(selected_machines)
    & state_events["_event_ts"].ge(start_ts) & state_events["_event_ts"].lt(end_ts)
].drop(columns="_event_ts")
batches = data["production_batches"].copy()
batches["_start"] = pd.to_datetime(batches["start_utc"], utc=True, errors="coerce")
batches["_end"] = pd.to_datetime(batches["end_utc"], utc=True, errors="coerce")
batch_ids = set(batches.loc[batches["_start"].lt(end_ts) & batches["_end"].ge(start_ts), "batch_id"])
data["production_batches"] = batches[batches["batch_id"].isin(batch_ids)].drop(columns=["_start", "_end"])
data["batch_machine"] = data["batch_machine"][data["batch_machine"]["batch_id"].isin(batch_ids)]
weather = data["weather_observations"].copy()
weather["_ts"] = pd.to_datetime(weather["timestamp_utc"], utc=True, errors="coerce")
data["weather_observations"] = weather[weather["_ts"].ge(start_ts) & weather["_ts"].lt(end_ts)].drop(columns="_ts")

if not selected_machines:
    st.warning("Select at least one machine in the sidebar to view role perspectives.")
    st.stop()

metrics = calculate_energy_metrics(data)
operator_tab, maintenance_tab, planner_tab, admin_tab = st.tabs([
    "Plant operator", "Maintenance / quality", "Production planner", "OT / IT administrator",
])

with operator_tab:
    st.subheader("Plant energy and demand")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Valid energy", f"{metrics['total_energy_kwh']:,.1f} kWh")
    k2.metric("Estimated energy cost", f"₹{metrics['total_cost_inr']:,.0f}")
    k3.metric("Peak demand", f"{metrics['peak_demand_kw']:,.1f} kW")
    k4.metric("Energy intensity", f"{metrics['energy_intensity_kwh_per_unit']:.4f} kWh/unit" if metrics["energy_intensity_kwh_per_unit"] is not None else "N/A")
    k5.metric("Idle energy", f"{metrics['idle_energy_kwh']:,.1f} kWh", f"{metrics['idle_energy_pct']:.1f}% of valid energy")
    st.caption(f"{start_date} to {end_date} UTC • {len(data['energy_readings']):,} meter rows • {len(selected_machines)} machine(s)")

    valid_readings, _ = clean_readings(data["energy_readings"], data["meter_machine"])
    valid_readings["timestamp_utc"] = pd.to_datetime(valid_readings["timestamp_utc"], utc=True, errors="coerce")
    valid_readings["date"] = valid_readings["timestamp_utc"].dt.date
    daily = valid_readings.groupby("date", as_index=False).agg(
        energy_kwh=("energy_kwh", "sum"), peak_demand_kw=("avg_power_kw", "max"),
    )
    st.subheader("Energy and demand trends")
    left, right = st.columns(2)
    left.plotly_chart(px.line(daily, x="date", y="energy_kwh", markers=True, title="Daily valid energy (kWh)"), width="stretch")
    right.plotly_chart(px.line(daily, x="date", y="peak_demand_kw", markers=True, title="Daily peak demand (kW)"), width="stretch")

    st.subheader("Machine performance")
    machine_summary = pd.DataFrame(metrics["machine_summary"])
    if not machine_summary.empty:
        left, right = st.columns(2)
        left.plotly_chart(px.bar(machine_summary, x="machine_name", y="energy_kwh", title="Energy by machine", hover_data=["cost_inr", "idle_kwh"]), width="stretch")
        right.plotly_chart(px.bar(machine_summary, x="machine_name", y="energy_intensity_kwh_per_unit", title="Meter energy per machine output", hover_data=["machine_output_units"]), width="stretch")
        st.dataframe(machine_summary, width="stretch", hide_index=True)
    else:
        st.info("No valid machine readings match these filters.")

with maintenance_tab:
    st.subheader("Maintenance events")
    if not data["maintenance_events"].empty:
        st.dataframe(data["maintenance_events"].sort_values("start_utc", ascending=False), width="stretch", hide_index=True)
    else:
        st.info("No maintenance events overlap this period and machine selection.")

    st.subheader("Exceptions and investigation guidance")
    anomaly_data = {key: value.copy() if isinstance(value, pd.DataFrame) else value for key, value in data.items()}
    if start_date != min_date or end_date != max_date or set(selected_machines) != set(machine_options):
        # Register totals are cumulative for the full source period, so omit them for a filtered slice.
        anomaly_data["meter_register_totals"] = raw_data["meter_register_totals"].iloc[0:0].copy()
    findings = [finding for finding in detect_anomalies(anomaly_data) if finding.get("severity") in selected_severities]
    if findings:
        st.dataframe(pd.DataFrame(findings).drop(columns=["entity_ids"]), width="stretch", hide_index=True)
        remediation = {
            "HIGH_IDLE_CONSUMPTION": "Review idle shutdown and standby settings against production and safety constraints.",
            "ENERGY_INTENSITY_SHIFT": "Compare process, recipe, maintenance, and equipment changes against the earlier baseline.",
            "DUPLICATE_READING": "Check source provenance and retain one authoritative interval after review.",
            "UNIT_KW_KWH_CONFUSION": "Confirm whether the source value is interval energy (kWh) or demand (kW), then normalize it.",
            "METER_MACHINE_HIERARCHY_VIOLATION": "Verify the effective-dated meter-to-machine assignment for the reading time.",
            "METER_TOTAL_MISMATCH": "Reconcile interval sums to the independent register and investigate gaps or duplicate intervals.",
            "TARIFF_TIMEZONE_MISMATCH": "Correct the tariff timezone before applying time-of-use rates.",
        }
        with st.expander("Recommended investigation"):
            for finding in findings:
                st.markdown(f"**{finding['issue_type']} ({finding['severity']})**  \n{remediation.get(finding['issue_type'], 'Review source rows and the documented rule.')}")
    else:
        st.success("No findings match the selected filters.")

    st.subheader("Energy-saving opportunities")
    recommendations = build_recommendations(data)
    rec_df = pd.DataFrame(recommendations)
    if not rec_df.empty:
        observation_days = max((end_date - start_date).days + 1, 1)
        rec_df["estimated_monthly_savings_kwh"] = rec_df["expected_savings_kwh"] / observation_days * 30
        rec_df["estimated_monthly_savings_inr"] = rec_df["expected_savings_inr"] / observation_days * 30
        st.dataframe(rec_df, width="stretch", hide_index=True)
        st.caption("Savings use 25% of observed valid idle energy and the matching time-of-use tariff where available. Monthly figures are a simple 30-day run-rate, not verified savings.")
    else:
        st.info("No recommendations meet the current thresholds.")

with planner_tab:
    st.subheader("Shift and tariff calendar")
    calendar_left, calendar_right = st.columns(2)
    calendar_left.dataframe(data["shifts"], width="stretch", hide_index=True)
    calendar_right.dataframe(data["tariffs"], width="stretch", hide_index=True)

    st.subheader("Production efficiency")
    production = analyze_production_efficiency(data)
    p1, p2, p3 = st.columns(3)
    p1.metric("Batches in period", len(data["production_batches"]))
    p2.metric("Batches analyzed", len(production["batch_detail"]))
    p3.metric("Production-only intensity", f"{production['overall_intensity']:.5f} kWh/unit" if production["overall_intensity"] is not None else "N/A")
    if production["batch_detail"]:
        machine_production = pd.DataFrame(production["machine_summary"])
        st.plotly_chart(px.bar(machine_production, x="machine_name", y="energy_kwh_per_unit", title="Production energy per output unit", hover_data=["batches", "output_units", "allocated_energy_kwh", "output_attainment_pct"]), width="stretch")
        st.dataframe(pd.DataFrame(production["batch_detail"]), width="stretch", hide_index=True)
        st.caption("Energy is allocated to batch windows, with partial intervals prorated. Production-only intensity excludes energy outside those windows.")
    else:
        st.info("No production batches overlap this period and machine selection.")

    st.subheader("Weather relationship with plant operations")
    weather_result = analyze_weather_energy(data)
    weather_observations = pd.DataFrame(weather_result["observations"])
    if not weather_observations.empty:
        left, right = st.columns(2)
        left.plotly_chart(px.scatter(weather_observations, x="temperature_c", y="energy_kwh", color="condition", hover_data=["timestamp_utc", "peak_demand_kw", "production_output_units"], title="Temperature and energy by 6-hour UTC bucket"), width="stretch")
        right.plotly_chart(px.scatter(weather_observations, x="temperature_c", y="energy_intensity_kwh_per_unit", color="condition", hover_data=["timestamp_utc", "production_output_units"], title="Temperature and production energy intensity"), width="stretch")
        correlation_rows = []
        for weather_field, by_metric in weather_result["correlations"].items():
            for metric, values in by_metric.items():
                correlation_rows.append({"weather_measure": weather_field, "operational_measure": metric,
                                         "pearson_r": values["pearson_r"], "sample_count": values["sample_count"]})
        st.dataframe(pd.DataFrame(correlation_rows), width="stretch", hide_index=True)
        st.caption(weather_result["note"])
    else:
        st.info(weather_result["note"])

with admin_tab:
    st.subheader("Data integrity and run traceability")
    report_path = PROJECT_ROOT / "data" / "processed" / "validation_summary.json"
    validation_report = read_json(report_path) or validate(PROJECT_ROOT / "data" / "raw")
    if validation_report["valid"]:
        st.success("Structural validation passed. Expected labeled exceptions are listed separately.")
    else:
        st.error("Structural validation found errors.")
    st.json(validation_report)
    generation = read_json(PROJECT_ROOT / "data" / "processed" / "generation_summary.json")
    reproducibility = read_json(PROJECT_ROOT / "data" / "processed" / "reproducibility_check.json")
    if generation:
        st.subheader("Generated source manifest")
        st.json(generation)
    if reproducibility:
        st.subheader("Same-seed reproducibility")
        st.json({key: value for key, value in reproducibility.items() if key != "sha256_run_1"})
    st.subheader("Recent state history")
    if not data["state_events"].empty:
        st.dataframe(data["state_events"].sort_values("event_utc", ascending=False).head(100), width="stretch", hide_index=True)
    else:
        st.info("No state changes in this date range and machine selection.")
    st.caption("Operational input tables and ground-truth evaluation labels are stored separately. This dashboard reports the validation output; it does not modify source history.")

st.divider()
st.caption("Synthetic operational data only. Estimated cost and savings use configured assumptions. Weather correlations are descriptive and do not prove causation.")
