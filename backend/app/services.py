from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from .models import (
    Device,
    SensorReading,
    IrrigationEvent,
    IrrigationSetting,
    Alert,
    Plant,
    PendingCommand,
    utcnow,
)
from .websocket_manager import manager

DEFAULT_DEVICE_ID = "esp32-greenpulse-01"
OFFLINE_THRESHOLD_SECONDS = 30
FLOW_RATE_L_PER_SEC = 0.02  # ~1.2 Liters/min micro-pump estimate
MAX_STORED_READINGS = 5000


def get_moisture_condition(moisture: float) -> str:
    """Categorizes soil moisture into standard operational condition text."""
    if moisture < 30.0:
        return "Dry – irrigation may be required."
    elif moisture < 45.0:
        return "Moisture is acceptable but should be monitored."
    elif moisture <= 75.0:
        return "Comfortable moisture range for the demonstration plant."
    else:
        return "High moisture – check the plant's watering requirements."


def initialize_default_data(db: Session):
    """Ensures default device, settings, and starter plants exist."""
    # Ensure default device exists
    device = db.query(Device).filter(Device.id == DEFAULT_DEVICE_ID).first()
    if not device:
        device = Device(
            id=DEFAULT_DEVICE_ID,
            device_name="GreenPulse ESP32 Station #1",
            device_status="offline",
            last_seen=utcnow() - timedelta(minutes=10),
            created_at=utcnow(),
        )
        db.add(device)

    # Ensure default settings exist
    settings = db.query(IrrigationSetting).filter(IrrigationSetting.device_id == DEFAULT_DEVICE_ID).first()
    if not settings:
        settings = IrrigationSetting(
            device_id=DEFAULT_DEVICE_ID,
            moisture_threshold=30.0,
            watering_duration_seconds=10,
            minimum_interval_seconds=60,
            max_watering_duration_seconds=30,
            automatic_mode=True,
            dry_adc=4095,
            wet_adc=1500,
            hysteresis=5.0,
            updated_at=utcnow(),
        )
        db.add(settings)

    # Seed demo plants if table empty
    plant_count = db.query(Plant).count()
    if plant_count == 0:
        starter_plants = [
            Plant(
                name="Cherry Tomato",
                plant_type="Solanum lycopersicum",
                location="Main Garden Bed #1",
                preferred_moisture_min=50.0,
                preferred_moisture_max=75.0,
                irrigation_threshold=35.0,
                notes="Requires consistently moist soil, especially during fruit set. High sun requirement.",
            ),
            Plant(
                name="Sweet Basil",
                plant_type="Ocimum basilicum",
                location="Herb Planter Box",
                preferred_moisture_min=45.0,
                preferred_moisture_max=70.0,
                irrigation_threshold=30.0,
                notes="Thrives in well-drained soil. Avoid over-soaking roots.",
            ),
            Plant(
                name="Monstera Deliciosa",
                plant_type="Tropical Foliage",
                location="Indoor Patio Corner",
                preferred_moisture_min=40.0,
                preferred_moisture_max=65.0,
                irrigation_threshold=25.0,
                notes="Allow top inch of soil to dry out between watering cycles.",
            ),
        ]
        db.add_all(starter_plants)

    db.commit()


def check_device_is_online(device: Optional[Device]) -> bool:
    """Calculates if the device is online based on recent heartbeat/reading."""
    if not device or not device.last_seen:
        return False
    # Handle timezone awareness
    now = utcnow()
    last_seen = device.last_seen
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    delta = (now - last_seen).total_seconds()
    return delta <= OFFLINE_THRESHOLD_SECONDS


def check_and_create_alert(
    db: Session,
    device_id: str,
    alert_type: str,
    message: str,
    severity: str = "warning",
    dedup_minutes: int = 15,
) -> Optional[Alert]:
    """Creates an alert with de-duplication to prevent flooding the database."""
    cutoff = utcnow() - timedelta(minutes=dedup_minutes)
    recent = (
        db.query(Alert)
        .filter(
            Alert.device_id == device_id,
            Alert.alert_type == alert_type,
            Alert.resolved_at.is_(None),
            Alert.created_at >= cutoff,
        )
        .first()
    )
    if recent:
        return None  # Suppress duplicate alert

    new_alert = Alert(
        device_id=device_id,
        alert_type=alert_type,
        message=message,
        severity=severity,
        created_at=utcnow(),
    )
    db.add(new_alert)
    db.commit()
    db.refresh(new_alert)
    return new_alert


def prune_old_readings(db: Session):
    """Enforces retention strategy to prevent unlimited database growth."""
    count = db.query(SensorReading).count()
    if count > MAX_STORED_READINGS:
        excess = count - MAX_STORED_READINGS
        old_ids = (
            db.query(SensorReading.id)
            .order_by(SensorReading.recorded_at.asc())
            .limit(excess)
            .all()
        )
        if old_ids:
            ids_to_del = [item[0] for item in old_ids]
            db.query(SensorReading).filter(SensorReading.id.in_(ids_to_del)).delete(synchronize_session=False)
            db.commit()


async def process_incoming_reading(
    db: Session,
    device_id: str,
    raw_adc_value: int,
    moisture_percentage: float,
    pump_status: str,
    irrigation_mode: str,
) -> SensorReading:
    """Processes, stores, and evaluates alerts for incoming sensor reading."""
    # Ensure device exists
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        device = Device(
            id=device_id,
            device_name=f"Node {device_id}",
            device_status="online",
            last_seen=utcnow(),
            created_at=utcnow(),
        )
        db.add(device)
    else:
        device.last_seen = utcnow()
        device.device_status = "online"

    # Clamp moisture percentage
    clamped_moisture = max(0.0, min(100.0, float(moisture_percentage)))

    # Create reading
    reading = SensorReading(
        device_id=device_id,
        raw_adc_value=raw_adc_value,
        moisture_percentage=clamped_moisture,
        pump_status=pump_status,
        irrigation_mode=irrigation_mode,
        recorded_at=utcnow(),
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)

    # Check settings for low moisture threshold
    settings = (
        db.query(IrrigationSetting)
        .filter(IrrigationSetting.device_id == device_id)
        .first()
    )
    threshold = settings.moisture_threshold if settings else 30.0

    # Auto alert generation
    if clamped_moisture < threshold:
        check_and_create_alert(
            db=db,
            device_id=device_id,
            alert_type="LOW_MOISTURE",
            message=f"Soil moisture critically low ({clamped_moisture:.1f}%). Threshold is {threshold:.1f}%.",
            severity="warning",
        )
    elif clamped_moisture >= (threshold + 5.0):
        # Auto-resolve previous low moisture alerts
        open_low_alerts = (
            db.query(Alert)
            .filter(
                Alert.device_id == device_id,
                Alert.alert_type == "LOW_MOISTURE",
                Alert.resolved_at.is_(None),
            )
            .all()
        )
        for a in open_low_alerts:
            a.resolved_at = utcnow()
        if open_low_alerts:
            db.commit()

    # Enforce database retention
    prune_old_readings(db)

    # Broadcast to WebSocket dashboard clients
    condition_text = get_moisture_condition(clamped_moisture)
    await manager.broadcast({
        "type": "SENSOR_READING",
        "data": {
            "device_id": device_id,
            "raw_adc_value": raw_adc_value,
            "moisture_percentage": clamped_moisture,
            "condition": condition_text,
            "pump_status": pump_status,
            "irrigation_mode": irrigation_mode,
            "recorded_at": reading.recorded_at.isoformat(),
            "is_online": True,
        }
    })

    return reading
