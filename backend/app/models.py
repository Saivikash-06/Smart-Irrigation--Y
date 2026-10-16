from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import relationship
from .database import Base


def utcnow():
    """Return current UTC time with timezone awareness."""
    return datetime.now(timezone.utc)


class Device(Base):
    __tablename__ = "devices"

    id = Column(String, primary_key=True, index=True)
    device_name = Column(String, default="GreenPulse ESP32 Node", nullable=False)
    device_status = Column(String, default="offline", nullable=False)  # "online" | "offline"
    last_seen = Column(DateTime, default=utcnow, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    readings = relationship("SensorReading", back_populates="device", cascade="all, delete-orphan")
    events = relationship("IrrigationEvent", back_populates="device", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="device", cascade="all, delete-orphan")
    commands = relationship("PendingCommand", back_populates="device", cascade="all, delete-orphan")


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    device_id = Column(String, ForeignKey("devices.id"), nullable=False, index=True)
    raw_adc_value = Column(Integer, nullable=False)
    moisture_percentage = Column(Float, nullable=False)
    pump_status = Column(String, default="OFF", nullable=False)  # "ON" | "OFF"
    irrigation_mode = Column(String, default="AUTO", nullable=False)  # "AUTO" | "MANUAL"
    recorded_at = Column(DateTime, default=utcnow, nullable=False, index=True)

    device = relationship("Device", back_populates="readings")


class IrrigationEvent(Base):
    __tablename__ = "irrigation_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    device_id = Column(String, ForeignKey("devices.id"), nullable=False, index=True)
    start_time = Column(DateTime, default=utcnow, nullable=False)
    end_time = Column(DateTime, nullable=True)
    moisture_before = Column(Float, nullable=False)
    moisture_after = Column(Float, nullable=True)
    irrigation_mode = Column(String, default="AUTO", nullable=False)  # "AUTO" | "MANUAL"
    status = Column(String, default="COMPLETED", nullable=False)  # "COMPLETED" | "INTERRUPTED" | "EMERGENCY_STOP"
    estimated_water_liters = Column(Float, default=0.0, nullable=False)

    device = relationship("Device", back_populates="events")


class IrrigationSetting(Base):
    __tablename__ = "irrigation_settings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    device_id = Column(String, default="esp32-greenpulse-01", nullable=False, unique=True)
    moisture_threshold = Column(Float, default=30.0, nullable=False)
    watering_duration_seconds = Column(Integer, default=10, nullable=False)
    minimum_interval_seconds = Column(Integer, default=60, nullable=False)
    max_watering_duration_seconds = Column(Integer, default=30, nullable=False)
    automatic_mode = Column(Boolean, default=True, nullable=False)
    dry_adc = Column(Integer, default=4095, nullable=False)
    wet_adc = Column(Integer, default=1500, nullable=False)
    hysteresis = Column(Float, default=5.0, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    device_id = Column(String, ForeignKey("devices.id"), nullable=False, index=True)
    alert_type = Column(String, nullable=False)  # LOW_MOISTURE, SENSOR_ERROR, DEVICE_OFFLINE, PUMP_OVERTIME, EMERGENCY_STOP
    message = Column(Text, nullable=False)
    severity = Column(String, default="warning", nullable=False)  # "info" | "warning" | "danger"
    created_at = Column(DateTime, default=utcnow, nullable=False, index=True)
    resolved_at = Column(DateTime, nullable=True)

    device = relationship("Device", back_populates="alerts")


class Plant(Base):
    __tablename__ = "plants"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)
    plant_type = Column(String, nullable=False)  # e.g., Tomato, Basil, Succulent, Fern
    location = Column(String, default="Main Garden Bed", nullable=False)
    preferred_moisture_min = Column(Float, default=45.0, nullable=False)
    preferred_moisture_max = Column(Float, default=75.0, nullable=False)
    irrigation_threshold = Column(Float, default=30.0, nullable=False)
    notes = Column(Text, default="", nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class PendingCommand(Base):
    __tablename__ = "pending_commands"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    device_id = Column(String, ForeignKey("devices.id"), nullable=False, index=True)
    command_type = Column(String, nullable=False)  # START_WATERING, STOP_WATERING, SET_MODE_AUTO, SET_MODE_MANUAL, EMERGENCY_STOP
    duration_seconds = Column(Integer, default=10, nullable=True)
    status = Column(String, default="PENDING", nullable=False)  # PENDING, EXECUTED, CANCELLED
    created_at = Column(DateTime, default=utcnow, nullable=False)
    executed_at = Column(DateTime, nullable=True)

    device = relationship("Device", back_populates="commands")
