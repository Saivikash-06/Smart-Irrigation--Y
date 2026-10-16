from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import (
    Device,
    SensorReading,
    IrrigationEvent,
    IrrigationSetting,
    Alert,
    utcnow,
)
from ..services import (
    DEFAULT_DEVICE_ID,
    process_incoming_reading,
    check_and_create_alert,
)

router = APIRouter(prefix="/api/demo", tags=["Demo Mode Simulator"])


@router.post("/simulate-reading")
async def simulate_demo_reading(
    moisture_percentage: float = 28.0,
    pump_status: str = "OFF",
    irrigation_mode: str = "AUTO",
    db: Session = Depends(get_db),
):
    """Injects a tagged demo/simulated reading for testing without physical ESP32."""
    # Convert moisture back to estimated raw ADC
    # moisture = (adc - 4095) / (1500 - 4095) * 100 => adc = 4095 + (moisture/100) * (1500 - 4095)
    raw_adc = int(4095 + (moisture_percentage / 100.0) * (1500 - 4095))
    raw_adc = max(0, min(4095, raw_adc))

    reading = await process_incoming_reading(
        db=db,
        device_id=DEFAULT_DEVICE_ID,
        raw_adc_value=raw_adc,
        moisture_percentage=moisture_percentage,
        pump_status=pump_status,
        irrigation_mode=irrigation_mode,
    )
    return {
        "status": "simulated",
        "reading_id": reading.id,
        "is_simulated": True,
        "moisture_percentage": reading.moisture_percentage,
        "raw_adc_value": reading.raw_adc_value,
        "pump_status": reading.pump_status,
        "recorded_at": reading.recorded_at.isoformat(),
        "disclaimer": "This is simulated demonstration telemetry, not live hardware sensor data.",
    }


@router.post("/trigger-scenario")
async def trigger_test_scenario(
    scenario_number: int,
    db: Session = Depends(get_db),
):
    """Triggers preset validation scenarios from prompt section 19."""
    settings = db.query(IrrigationSetting).filter(IrrigationSetting.device_id == DEFAULT_DEVICE_ID).first()
    if not settings:
        settings = IrrigationSetting(device_id=DEFAULT_DEVICE_ID)
        db.add(settings)
        db.commit()

    device = db.query(Device).filter(Device.id == DEFAULT_DEVICE_ID).first()

    if scenario_number == 1:
        # Scenario 1: Moisture is 60%. Expected: Pump OFF.
        return await simulate_demo_reading(moisture_percentage=60.0, pump_status="OFF", irrigation_mode="AUTO", db=db)

    elif scenario_number == 2:
        # Scenario 2: Moisture falls below 30%. Expected: Auto watering starts if safety permits
        return await simulate_demo_reading(moisture_percentage=22.5, pump_status="ON", irrigation_mode="AUTO", db=db)

    elif scenario_number == 3:
        # Scenario 3: Moisture rises above configured stop threshold. Expected: Pump OFF
        return await simulate_demo_reading(moisture_percentage=55.0, pump_status="OFF", irrigation_mode="AUTO", db=db)

    elif scenario_number == 5:
        # Scenario 5: User activates emergency stop
        check_and_create_alert(
            db=db,
            device_id=DEFAULT_DEVICE_ID,
            alert_type="EMERGENCY_STOP",
            message="EMERGENCY STOP manually triggered. Pump deactivated, auto-irrigation locked.",
            severity="danger",
        )
        settings.automatic_mode = False
        db.commit()
        return {"status": "emergency_stop_triggered", "pump_status": "OFF", "automatic_mode": False}

    elif scenario_number == 6:
        # Scenario 6: Device disconnects (offline)
        from datetime import timedelta
        if device:
            device.last_seen = utcnow() - timedelta(minutes=5)
            device.device_status = "offline"
            db.commit()
        check_and_create_alert(
            db=db,
            device_id=DEFAULT_DEVICE_ID,
            alert_type="DEVICE_OFFLINE",
            message="Device offline – displaying the last available reading.",
            severity="warning",
        )
        return {"status": "device_marked_offline", "is_online": False}

    elif scenario_number == 7:
        # Scenario 7: Sensor returns invalid data
        check_and_create_alert(
            db=db,
            device_id=DEFAULT_DEVICE_ID,
            alert_type="SENSOR_ERROR",
            message="Sensor ADC reading invalid or disconnected. Irrigation suspended for safety.",
            severity="danger",
        )
        return {"status": "sensor_error_simulated", "safe_state_engaged": True}

    else:
        raise HTTPException(status_code=400, detail=f"Scenario {scenario_number} not recognized")
