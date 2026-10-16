from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class SensorReadingCreate(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=100)
    raw_adc_value: int = Field(..., ge=0, le=4095, description="ESP32 12-bit ADC reading (0-4095)")
    moisture_percentage: float = Field(..., ge=0.0, le=100.0, description="Calculated moisture percentage (0-100%)")
    pump_status: str = Field(default="OFF", description="'ON' or 'OFF'")
    irrigation_mode: str = Field(default="AUTO", description="'AUTO' or 'MANUAL'")

    @field_validator("pump_status")
    @classmethod
    def validate_pump(cls, v: str) -> str:
        upper_v = v.strip().upper()
        if upper_v not in ("ON", "OFF"):
            raise ValueError("pump_status must be 'ON' or 'OFF'")
        return upper_v

    @field_validator("irrigation_mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        upper_v = v.strip().upper()
        if upper_v not in ("AUTO", "MANUAL"):
            raise ValueError("irrigation_mode must be 'AUTO' or 'MANUAL'")
        return upper_v


class SensorReadingResponse(BaseModel):
    id: int
    device_id: str
    raw_adc_value: int
    moisture_percentage: float
    pump_status: str
    irrigation_mode: str
    recorded_at: datetime

    class Config:
        from_attributes = True


class DeviceStatusResponse(BaseModel):
    device_id: str
    device_name: str
    is_online: bool
    status: str
    last_seen: datetime
    pump_status: str
    irrigation_mode: str
    current_moisture: Optional[float] = None
    last_adc_value: Optional[int] = None


class IrrigationCommandRequest(BaseModel):
    device_id: Optional[str] = "esp32-greenpulse-01"
    command: str = Field(..., description="START, STOP, SET_MODE_AUTO, SET_MODE_MANUAL, EMERGENCY_STOP")
    duration_seconds: Optional[int] = Field(default=10, ge=1, le=120)

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: str) -> str:
        valid_commands = {
            "START",
            "STOP",
            "START_WATERING",
            "STOP_WATERING",
            "SET_MODE_AUTO",
            "SET_MODE_MANUAL",
            "EMERGENCY_STOP",
        }
        upper_v = v.strip().upper()
        if upper_v not in valid_commands:
            raise ValueError(f"Invalid command. Must be one of: {', '.join(valid_commands)}")
        return upper_v


class IrrigationCommandResponse(BaseModel):
    success: bool
    message: str
    command: str
    command_id: Optional[int] = None
    target_device: str


class IrrigationSettingsUpdate(BaseModel):
    device_name: Optional[str] = None
    moisture_threshold: Optional[float] = Field(None, ge=5.0, le=95.0)
    watering_duration_seconds: Optional[int] = Field(None, ge=1, le=120)
    minimum_interval_seconds: Optional[int] = Field(None, ge=10, le=86400)
    max_watering_duration_seconds: Optional[int] = Field(None, ge=5, le=300)
    automatic_mode: Optional[bool] = None
    dry_adc: Optional[int] = Field(None, ge=2000, le=4095)
    wet_adc: Optional[int] = Field(None, ge=0, le=3000)
    hysteresis: Optional[float] = Field(None, ge=1.0, le=20.0)


class IrrigationSettingsResponse(BaseModel):
    id: int
    device_id: str
    device_name: str
    moisture_threshold: float
    watering_duration_seconds: int
    minimum_interval_seconds: int
    max_watering_duration_seconds: int
    automatic_mode: bool
    dry_adc: int
    wet_adc: int
    hysteresis: float
    updated_at: datetime

    class Config:
        from_attributes = True


class IrrigationEventCreate(BaseModel):
    device_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    moisture_before: float
    moisture_after: Optional[float] = None
    irrigation_mode: str = "AUTO"
    status: str = "COMPLETED"
    estimated_water_liters: Optional[float] = None


class IrrigationEventResponse(BaseModel):
    id: int
    device_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    moisture_before: float
    moisture_after: Optional[float] = None
    irrigation_mode: str
    status: str
    estimated_water_liters: float

    class Config:
        from_attributes = True


class AlertResponse(BaseModel):
    id: int
    device_id: str
    alert_type: str
    message: str
    severity: str
    created_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PlantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    plant_type: str = Field(..., min_length=1, max_length=100)
    location: str = Field(default="Main Garden Bed", max_length=100)
    preferred_moisture_min: float = Field(default=45.0, ge=0.0, le=100.0)
    preferred_moisture_max: float = Field(default=75.0, ge=0.0, le=100.0)
    irrigation_threshold: float = Field(default=30.0, ge=5.0, le=95.0)
    notes: Optional[str] = ""


class PlantUpdate(BaseModel):
    name: Optional[str] = None
    plant_type: Optional[str] = None
    location: Optional[str] = None
    preferred_moisture_min: Optional[float] = None
    preferred_moisture_max: Optional[float] = None
    irrigation_threshold: Optional[float] = None
    notes: Optional[str] = None


class PlantResponse(BaseModel):
    id: int
    name: str
    plant_type: str
    location: str
    preferred_moisture_min: float
    preferred_moisture_max: float
    irrigation_threshold: float
    notes: str
    created_at: datetime

    class Config:
        from_attributes = True


class DashboardSummaryResponse(BaseModel):
    soil_moisture_percentage: float
    raw_adc_value: int
    moisture_condition: str
    pump_status: str
    irrigation_mode: str
    automatic_mode: bool
    total_watering_events: int
    total_water_liters: float
    last_sensor_update: Optional[datetime] = None
    device_online: bool
    device_status: str
    active_alerts_count: int
    threshold: float
    is_emergency_stop: bool
