from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import (
    Device,
    SensorReading,
    IrrigationEvent,
    IrrigationSetting,
    Alert,
    PendingCommand,
    utcnow,
)
from ..services import (
    DEFAULT_DEVICE_ID,
    check_device_is_online,
    get_moisture_condition,
)

router = APIRouter(prefix="/api", tags=["Dashboard"])


@router.get("/dashboard")
def get_dashboard_summary(device_id: str = DEFAULT_DEVICE_ID, db: Session = Depends(get_db)):
    """Aggregates all real-time metrics, telemetry, and system states for the main dashboard."""
    device = db.query(Device).filter(Device.id == device_id).first()
    is_online = check_device_is_online(device)

    # Latest reading
    latest_reading = (
        db.query(SensorReading)
        .filter(SensorReading.device_id == device_id)
        .order_by(SensorReading.recorded_at.desc())
        .first()
    )

    # Active settings
    settings = db.query(IrrigationSetting).filter(IrrigationSetting.device_id == device_id).first()
    threshold = settings.moisture_threshold if settings else 30.0
    auto_mode = settings.automatic_mode if settings else True

    # Total watering events & water consumption
    total_events = db.query(IrrigationEvent).filter(IrrigationEvent.device_id == device_id).count()
    water_rows = (
        db.query(IrrigationEvent.estimated_water_liters)
        .filter(IrrigationEvent.device_id == device_id)
        .all()
    )
    total_water = round(sum(r[0] for r in water_rows if r[0] is not None), 2)

    # Recent watering events (last 5)
    recent_events = (
        db.query(IrrigationEvent)
        .filter(IrrigationEvent.device_id == device_id)
        .order_by(IrrigationEvent.start_time.desc())
        .limit(5)
        .all()
    )

    # Active un-resolved alerts (last 5)
    active_alerts = (
        db.query(Alert)
        .filter(Alert.device_id == device_id, Alert.resolved_at.is_(None))
        .order_by(Alert.created_at.desc())
        .limit(5)
        .all()
    )

    # Check emergency stop active in open alerts
    emergency_active = (
        db.query(Alert)
        .filter(
            Alert.device_id == device_id,
            Alert.alert_type == "EMERGENCY_STOP",
            Alert.resolved_at.is_(None),
        )
        .first()
        is not None
    )

    # Recent readings for moisture trend chart (last 20 readings)
    recent_readings = (
        db.query(SensorReading)
        .filter(SensorReading.device_id == device_id)
        .order_by(SensorReading.recorded_at.desc())
        .limit(20)
        .all()
    )
    recent_readings.reverse()

    # Fallback values if no reading recorded yet
    current_moisture = latest_reading.moisture_percentage if latest_reading else 0.0
    raw_adc = latest_reading.raw_adc_value if latest_reading else 4095
    pump_status = latest_reading.pump_status if latest_reading else "OFF"
    irrigation_mode = (
        latest_reading.irrigation_mode
        if latest_reading
        else ("AUTO" if auto_mode else "MANUAL")
    )

    return {
        "device": {
            "id": device_id,
            "name": device.device_name if device else "GreenPulse ESP32 Station",
            "is_online": is_online,
            "status": "online" if is_online else "offline",
            "last_seen": device.last_seen.isoformat() if (device and device.last_seen) else None,
            "offline_notice": (
                "Device offline – displaying the last available reading."
                if not is_online
                else None
            ),
        },
        "sensor": {
            "current_moisture": current_moisture,
            "raw_adc": raw_adc,
            "condition": get_moisture_condition(current_moisture),
            "pump_status": pump_status,
            "irrigation_mode": irrigation_mode,
            "last_update": latest_reading.recorded_at.isoformat() if latest_reading else None,
        },
        "irrigation": {
            "threshold": threshold,
            "automatic_mode": auto_mode,
            "watering_duration_seconds": settings.watering_duration_seconds if settings else 10,
            "minimum_interval_seconds": settings.minimum_interval_seconds if settings else 60,
            "total_watering_events": total_events,
            "total_water_liters": total_water,
            "is_emergency_stop": emergency_active,
        },
        "chart_data": [
            {
                "timestamp": r.recorded_at.isoformat(),
                "moisture": r.moisture_percentage,
                "pump_status": r.pump_status,
            }
            for r in recent_readings
        ],
        "recent_activity": [
            {
                "id": ev.id,
                "start_time": ev.start_time.isoformat(),
                "end_time": ev.end_time.isoformat() if ev.end_time else None,
                "moisture_before": ev.moisture_before,
                "moisture_after": ev.moisture_after,
                "irrigation_mode": ev.irrigation_mode,
                "status": ev.status,
                "estimated_water_liters": ev.estimated_water_liters,
            }
            for ev in recent_events
        ],
        "active_alerts": [
            {
                "id": al.id,
                "alert_type": al.alert_type,
                "message": al.message,
                "severity": al.severity,
                "created_at": al.created_at.isoformat(),
            }
            for al in active_alerts
        ],
    }
