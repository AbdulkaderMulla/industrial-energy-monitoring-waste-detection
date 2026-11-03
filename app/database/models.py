from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database.connection import Base

class Plant(Base):
    __tablename__ = "plants"
    plant_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str] = mapped_column(String, nullable=False)
    timezone: Mapped[str] = mapped_column(String, default="UTC")
    status: Mapped[str] = mapped_column(String, default="ACTIVE")

class Meter(Base):
    __tablename__ = "meters"
    meter_id: Mapped[str] = mapped_column(String, primary_key=True)
    plant_id: Mapped[str] = mapped_column(ForeignKey("plants.plant_id"), nullable=False)
    meter_name: Mapped[str] = mapped_column(String, nullable=False)
    unit: Mapped[str] = mapped_column(String, default="kWh_interval")
    cadence_minutes: Mapped[int] = mapped_column(Integer, default=15)
    status: Mapped[str] = mapped_column(String, default="ACTIVE")

class Machine(Base):
    __tablename__ = "machines"
    machine_id: Mapped[str] = mapped_column(String, primary_key=True)
    plant_id: Mapped[str] = mapped_column(ForeignKey("plants.plant_id"), nullable=False)
    machine_name: Mapped[str] = mapped_column(String, nullable=False)
    machine_type: Mapped[str] = mapped_column(String, nullable=False)
    rated_power_kw: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, default="ACTIVE")

class MeterMachine(Base):
    __tablename__ = "meter_machine"
    assignment_id: Mapped[str] = mapped_column(String, primary_key=True)
    meter_id: Mapped[str] = mapped_column(ForeignKey("meters.meter_id"), nullable=False)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.machine_id"), nullable=False)
    effective_from: Mapped[str] = mapped_column(String, nullable=False)
    effective_to: Mapped[str | None] = mapped_column(String)

class EnergyReading(Base):
    __tablename__ = "energy_readings"
    row_id: Mapped[str] = mapped_column(String, primary_key=True)
    reading_id: Mapped[str] = mapped_column(String, nullable=False)
    meter_id: Mapped[str] = mapped_column(ForeignKey("meters.meter_id"), nullable=False)
    machine_id: Mapped[str | None] = mapped_column(ForeignKey("machines.machine_id"))
    timestamp_utc: Mapped[str] = mapped_column(String, nullable=False)
    energy_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    avg_power_kw: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String, default="kWh_interval")
    state: Mapped[str] = mapped_column(String, default="RUNNING")
    shift_id: Mapped[str | None] = mapped_column(ForeignKey("shifts.shift_id"))

class ProductionBatch(Base):
    __tablename__ = "production_batches"
    batch_id: Mapped[str] = mapped_column(String, primary_key=True)
    plant_id: Mapped[str] = mapped_column(ForeignKey("plants.plant_id"), nullable=False)
    shift_id: Mapped[str | None] = mapped_column(ForeignKey("shifts.shift_id"))
    start_utc: Mapped[str] = mapped_column(String, nullable=False)
    end_utc: Mapped[str] = mapped_column(String, nullable=False)
    planned_output_units: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_output_units: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, default="COMPLETED")

class BatchMachine(Base):
    __tablename__ = "batch_machine"
    batch_machine_id: Mapped[str] = mapped_column(String, primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("production_batches.batch_id"), nullable=False)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.machine_id"), nullable=False)
    output_units: Mapped[int] = mapped_column(Integer, nullable=False)

class Shift(Base):
    __tablename__ = "shifts"
    shift_id: Mapped[str] = mapped_column(String, primary_key=True)
    plant_id: Mapped[str] = mapped_column(ForeignKey("plants.plant_id"), nullable=False)
    shift_name: Mapped[str] = mapped_column(String, nullable=False)
    start_time: Mapped[str] = mapped_column(String, nullable=False)
    end_time: Mapped[str] = mapped_column(String, nullable=False)
    effective_from: Mapped[str] = mapped_column(String, nullable=False)
    effective_to: Mapped[str | None] = mapped_column(String)

class Tariff(Base):
    __tablename__ = "tariffs"
    tariff_id: Mapped[str] = mapped_column(String, primary_key=True)
    plant_id: Mapped[str] = mapped_column(ForeignKey("plants.plant_id"), nullable=False)
    tariff_name: Mapped[str] = mapped_column(String, nullable=False)
    start_hour_utc: Mapped[int] = mapped_column(Integer, nullable=False)
    end_hour_utc: Mapped[int] = mapped_column(Integer, nullable=False)
    rate_inr_per_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    effective_from: Mapped[str] = mapped_column(String, nullable=False)
    effective_to: Mapped[str | None] = mapped_column(String)
    timezone: Mapped[str] = mapped_column(String, default="UTC")

class WeatherObservation(Base):
    __tablename__ = "weather_observations"
    weather_id: Mapped[str] = mapped_column(String, primary_key=True)
    plant_id: Mapped[str] = mapped_column(ForeignKey("plants.plant_id"), nullable=False)
    timestamp_utc: Mapped[str] = mapped_column(String, nullable=False)
    temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    humidity_pct: Mapped[float] = mapped_column(Float, nullable=False)
    condition: Mapped[str] = mapped_column(String, nullable=False)

class MaintenanceEvent(Base):
    __tablename__ = "maintenance_events"
    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.machine_id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    start_utc: Mapped[str] = mapped_column(String, nullable=False)
    end_utc: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="")

class Recommendation(Base):
    __tablename__ = "recommendations"
    recommendation_id: Mapped[str] = mapped_column(String, primary_key=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.machine_id"), nullable=False)
    created_utc: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    expected_savings_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    expected_savings_inr: Mapped[float] = mapped_column(Float, nullable=False)
    priority: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="OPEN")

class MeterRegisterTotal(Base):
    """Independent cumulative register snapshot used for reconciliation."""
    __tablename__ = "meter_register_totals"
    meter_id: Mapped[str] = mapped_column(ForeignKey("meters.meter_id"), primary_key=True)
    register_total_kwh: Mapped[float] = mapped_column(Float, nullable=False)

class StateEvent(Base):
    __tablename__ = "state_events"
    state_event_id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    old_state: Mapped[str | None] = mapped_column(String)
    new_state: Mapped[str] = mapped_column(String, nullable=False)
    event_utc: Mapped[str] = mapped_column(String, nullable=False)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

