from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import SensorReading, Device, utcnow
from ..schemas import SensorReadingCreate, SensorReadingResponse
from ..services import process_incoming_reading, DEFAULT_DEVICE_ID

router = APIRouter(prefix="/api/sensor", tags=["Sensors"])


@router.post("/readings", response_model=SensorReadingResponse, status_code=201)
async def post_sensor_reading(reading_in: SensorReadingCreate, db: Session = Depends(get_db)):
    """Receives, validates, and persists telemetry reading from ESP32 or simulation."""
    # Validate raw ADC
    if reading_in.raw_adc_value < 0 or reading_in.raw_adc_value > 4095:
        raise HTTPException(status_code=422, detail="ADC reading out of 12-bit range (0-4095)")

    reading = await process_incoming_reading(
        db=db,
        device_id=reading_in.device_id,
        raw_adc_value=reading_in.raw_adc_value,
        moisture_percentage=reading_in.moisture_percentage,
        pump_status=reading_in.pump_status,
        irrigation_mode=reading_in.irrigation_mode,
    )
    return reading


@router.get("/latest", response_model=SensorReadingResponse)
def get_latest_sensor_reading(device_id: str = DEFAULT_DEVICE_ID, db: Session = Depends(get_db)):
    """Fetch the single latest recorded sensor telemetry entry."""
    reading = (
        db.query(SensorReading)
        .filter(SensorReading.device_id == device_id)
        .order_by(SensorReading.recorded_at.desc())
        .first()
    )
    if not reading:
        raise HTTPException(status_code=404, detail="No sensor readings available for this device")
    return reading


@router.get("/history", response_model=List[SensorReadingResponse])
def get_sensor_history(
    device_id: str = DEFAULT_DEVICE_ID,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    """Retrieve historical sensor readings with pagination and time filtering."""
    query = db.query(SensorReading).filter(SensorReading.device_id == device_id)

    if start_time:
        query = query.filter(SensorReading.recorded_at >= start_time)
    if end_time:
        query = query.filter(SensorReading.recorded_at <= end_time)

    # Return chronological order (asc) for charts if requested or latest first
    readings = (
        query.order_by(SensorReading.recorded_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    # Reverse to return chronological order
    readings.reverse()
    return readings
