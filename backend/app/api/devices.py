from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Device, SensorReading, IrrigationSetting, utcnow
from ..schemas import DeviceStatusResponse
from ..services import check_device_is_online, DEFAULT_DEVICE_ID

router = APIRouter(prefix="/api", tags=["Devices"])


@router.get("/health")
def get_health():
    """Health check endpoint to verify backend operational readiness."""
    return {
        "status": "healthy",
        "timestamp": utcnow().isoformat(),
        "service": "GreenPulse Smart Irrigation Backend",
        "version": "1.0.0",
    }


@router.get("/device/status", response_model=DeviceStatusResponse)
def get_device_status(device_id: str = DEFAULT_DEVICE_ID, db: Session = Depends(get_db)):
    """Return device connectivity status, last-seen timestamp, and active state."""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    is_online = check_device_is_online(device)
    device.device_status = "online" if is_online else "offline"
    db.commit()

    # Get latest reading if available
    latest_reading = (
        db.query(SensorReading)
        .filter(SensorReading.device_id == device_id)
        .order_by(SensorReading.recorded_at.desc())
        .first()
    )

    settings = (
        db.query(IrrigationSetting)
        .filter(IrrigationSetting.device_id == device_id)
        .first()
    )
    irrigation_mode = "AUTO" if (settings and settings.automatic_mode) else "MANUAL"
    if latest_reading and latest_reading.irrigation_mode:
        irrigation_mode = latest_reading.irrigation_mode

    return DeviceStatusResponse(
        device_id=device.id,
        device_name=device.device_name,
        is_online=is_online,
        status="online" if is_online else "offline",
        last_seen=device.last_seen,
        pump_status=latest_reading.pump_status if latest_reading else "OFF",
        irrigation_mode=irrigation_mode,
        current_moisture=latest_reading.moisture_percentage if latest_reading else None,
        last_adc_value=latest_reading.raw_adc_value if latest_reading else None,
    )


@router.post("/device/heartbeat")
def device_heartbeat(device_id: str = DEFAULT_DEVICE_ID, db: Session = Depends(get_db)):
    """Update device last-seen timestamp to maintain online status."""
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

    db.commit()
    return {"status": "acknowledged", "last_seen": device.last_seen.isoformat()}
