from fastapi import FastAPI, HTTPException, Query
from pathlib import Path
from app.services.analytics import load_data, calculate_energy_metrics, detect_anomalies, build_recommendations, analyze_production_efficiency, analyze_weather_energy
from validation.validate_data import validate
from app.database.connection import engine
from sqlalchemy import inspect

app = FastAPI(title="Industrial Energy Monitoring API", version="1.0.0")

@app.get("/")
def root():
    return {"message":"Industrial Energy Monitoring & Waste Detection API","docs":"/docs"}

@app.get("/health")
def health():
    return {"status":"ok"}

@app.get("/validation")
def validation():
    try:
        return validate()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset not found. Run the generator first.")

@app.get("/analytics/overview")
def overview():
    try:
        return calculate_energy_metrics(load_data())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset not found. Run the generator first.")

@app.get("/anomalies")
def anomalies(severity: str | None = Query(default=None, pattern="^(HIGH|MEDIUM|LOW)$")):
    try:
        findings = detect_anomalies(load_data())
        if severity:
            findings = [item for item in findings if item.get("severity") == severity]
        return {"findings": findings}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset not found. Run the generator first.")

@app.get("/recommendations")
def recommendations():
    try:
        return {"recommendations":build_recommendations(load_data())}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset not found. Run the generator first.")


@app.get("/analytics/production")
def production_analytics():
    try:
        return analyze_production_efficiency(load_data())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset not found. Run the generator first.")


@app.get("/analytics/weather")
def weather_analytics():
    try:
        return analyze_weather_energy(load_data())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset not found. Run the generator first.")


@app.get("/database/status")
def database_status():
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        table_names = inspect(engine).get_table_names()
        return {
            "status": "connected",
            "schema_initialized": bool(table_names),
            "table_count": len(table_names),
            "tables": table_names,
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {type(exc).__name__}")
