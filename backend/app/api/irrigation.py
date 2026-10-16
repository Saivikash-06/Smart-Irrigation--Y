import csv
import io
from typing import Optional, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import desc

from ..database import get_db
from ..models import (
    IrrigationSetting,
    IrrigationEvent,
    PendingCommand,
    Device,
    SensorReading,
    Alert,
    utcnow,
)
from ..schemas import (
    IrrigationSettingsResponse,
    IrrigationSettingsUpdate,
    IrrigationCommandRequest,
    IrrigationCommandResponse,
    IrrigationEventCreate,
    IrrigationEventResponse,
)
from ..services import (
    DEFAULT_DEVICE_ID,
    FLOW_RATE_L_PER_SEC,
    check_device_is_online,
    check_and_create_alert,
)
from ..websocket_manager import manager

router = APIRouter(prefix="/api/irrigation", tags=["Irrigation Control"])


@router.get("/settings", response_model=IrrigationSettingsResponse)
def get_irrigation_settings(device_id: str = DEFAULT_DEVICE_ID, db: Session = Depends(get_db)):
    """Fetch active irrigation parameters, calibration values, and thresholds."""
    settings = db.query(IrrigationSetting).filter(IrrigationSetting.device_id == device_id).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    device = db.query(Device).filter(Device.id == device_id).first()
    device_name = device.device_name if device else "GreenPulse ESP32 Station"

    return IrrigationSettingsResponse(
        id=settings.id,
        device_id=settings.device_id,
        device_name=device_name,
        moisture_threshold=settings.moisture_threshold,
        watering_duration_seconds=settings.watering_duration_seconds,
        minimum_interval_seconds=settings.minimum_interval_seconds,
        max_watering_duration_seconds=settings.max_watering_duration_seconds,
        automatic_mode=settings.automatic_mode,
        dry_adc=settings.dry_adc,
        wet_adc=settings.wet_adc,
        hysteresis=settings.hysteresis,
        updated_at=settings.updated_at,
    )


@router.put("/settings", response_model=IrrigationSettingsResponse)
async def update_irrigation_settings(
    settings_in: IrrigationSettingsUpdate,
    device_id: str = DEFAULT_DEVICE_ID,
    db: Session = Depends(get_db),
):
    """Update irrigation thresholds, watering durations, and ADC calibration parameters."""
    settings = db.query(IrrigationSetting).filter(IrrigationSetting.device_id == device_id).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    device = db.query(Device).filter(Device.id == device_id).first()
    if settings_in.device_name and device:
        device.device_name = settings_in.device_name

    if settings_in.moisture_threshold is not None:
        settings.moisture_threshold = settings_in.moisture_threshold
    if settings_in.watering_duration_seconds is not None:
        settings.watering_duration_seconds = settings_in.watering_duration_seconds
    if settings_in.minimum_interval_seconds is not None:
        settings.minimum_interval_seconds = settings_in.minimum_interval_seconds
    if settings_in.max_watering_duration_seconds is not None:
        settings.max_watering_duration_seconds = settings_in.max_watering_duration_seconds
    if settings_in.automatic_mode is not None:
        settings.automatic_mode = settings_in.automatic_mode
    if settings_in.dry_adc is not None:
        settings.dry_adc = settings_in.dry_adc
    if settings_in.wet_adc is not None:
        settings.wet_adc = settings_in.wet_adc
    if settings_in.hysteresis is not None:
        settings.hysteresis = settings_in.hysteresis

    settings.updated_at = utcnow()
    db.commit()
    db.refresh(settings)

    # Broadcast updated settings to connected clients
    await manager.broadcast({
        "type": "SETTINGS_UPDATED",
        "data": {
            "device_id": device_id,
            "moisture_threshold": settings.moisture_threshold,
            "automatic_mode": settings.automatic_mode,
            "watering_duration_seconds": settings.watering_duration_seconds,
        }
    })

    device_name = device.device_name if device else "GreenPulse ESP32 Station"
    return IrrigationSettingsResponse(
        id=settings.id,
        device_id=settings.device_id,
        device_name=device_name,
        moisture_threshold=settings.moisture_threshold,
        watering_duration_seconds=settings.watering_duration_seconds,
        minimum_interval_seconds=settings.minimum_interval_seconds,
        max_watering_duration_seconds=settings.max_watering_duration_seconds,
        automatic_mode=settings.automatic_mode,
        dry_adc=settings.dry_adc,
        wet_adc=settings.wet_adc,
        hysteresis=settings.hysteresis,
        updated_at=settings.updated_at,
    )


@router.post("/commands", response_model=IrrigationCommandResponse)
async def submit_irrigation_command(
    cmd_req: IrrigationCommandRequest,
    db: Session = Depends(get_db),
):
    """Validate and dispatch an irrigation command (START, STOP, AUTO, MANUAL, EMERGENCY_STOP)."""
    device_id = cmd_req.device_id or DEFAULT_DEVICE_ID
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not registered")

    cmd_type = cmd_req.command.upper()
    settings = db.query(IrrigationSetting).filter(IrrigationSetting.device_id == device_id).first()

    # Enforce safety max duration
    duration = cmd_req.duration_seconds or 10
    if settings and duration > settings.max_watering_duration_seconds:
        duration = settings.max_watering_duration_seconds

    # Handle Emergency Stop specifically
    if cmd_type == "EMERGENCY_STOP":
        check_and_create_alert(
            db=db,
            device_id=device_id,
            alert_type="EMERGENCY_STOP",
            message="Emergency Stop activated! All irrigation halted immediately.",
            severity="danger",
        )
        if settings:
            settings.automatic_mode = False
            db.commit()

    elif cmd_type in ("SET_MODE_AUTO", "AUTO"):
        if settings:
            settings.automatic_mode = True
            db.commit()
    elif cmd_type in ("SET_MODE_MANUAL", "MANUAL"):
        if settings:
            settings.automatic_mode = False
            db.commit()

    # Create pending command entry for hardware consumption
    pending_cmd = PendingCommand(
        device_id=device_id,
        command_type=cmd_type,
        duration_seconds=duration,
        status="PENDING",
        created_at=utcnow(),
    )
    db.add(pending_cmd)
    db.commit()
    db.refresh(pending_cmd)

    # Broadcast command to WebSocket subscribers (including ESP32 or web dashboard)
    await manager.broadcast({
        "type": "IRRIGATION_COMMAND",
        "data": {
            "command_id": pending_cmd.id,
            "device_id": device_id,
            "command": cmd_type,
            "duration_seconds": duration,
        }
    })

    return IrrigationCommandResponse(
        success=True,
        message=f"Command '{cmd_type}' registered and queued for device {device_id}.",
        command=cmd_type,
        command_id=pending_cmd.id,
        target_device=device_id,
    )


@router.get("/commands/pending")
def get_pending_commands(device_id: str = DEFAULT_DEVICE_ID, db: Session = Depends(get_db)):
    """Used by ESP32 or simulation agent to retrieve unexecuted pending commands."""
    commands = (
        db.query(PendingCommand)
        .filter(PendingCommand.device_id == device_id, PendingCommand.status == "PENDING")
        .order_by(PendingCommand.created_at.asc())
        .all()
    )
    return [
        {
            "id": cmd.id,
            "command": cmd.command_type,
            "duration_seconds": cmd.duration_seconds,
            "created_at": cmd.created_at.isoformat(),
        }
        for cmd in commands
    ]


@router.post("/commands/ack")
async def acknowledge_command(
    command_id: int,
    status: str = "EXECUTED",
    db: Session = Depends(get_db),
):
    """Device sends acknowledgement after executing or cancelling a queued command."""
    cmd = db.query(PendingCommand).filter(PendingCommand.id == command_id).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")

    cmd.status = status
    cmd.executed_at = utcnow()
    db.commit()

    await manager.broadcast({
        "type": "COMMAND_ACK",
        "data": {
            "command_id": cmd.id,
            "device_id": cmd.device_id,
            "status": status,
        }
    })
    return {"status": "ok", "command_id": cmd.id}


@router.post("/events", response_model=IrrigationEventResponse, status_code=201)
async def record_irrigation_event(
    event_in: IrrigationEventCreate,
    db: Session = Depends(get_db),
):
    """Record a completed watering event with before/after moisture and estimated water usage."""
    # Calculate estimated water if not provided
    water_liters = event_in.estimated_water_liters
    if water_liters is None:
        if event_in.end_time:
            # Ensure aware or naive calculation
            start_t = event_in.start_time
            end_t = event_in.end_time
            if start_t.tzinfo is None:
                start_t = start_t.replace(tzinfo=timezone.utc)
            if end_t.tzinfo is None:
                end_t = end_t.replace(tzinfo=timezone.utc)
            seconds = max(1.0, (end_t - start_t).total_seconds())
            water_liters = round(seconds * FLOW_RATE_L_PER_SEC, 2)
        else:
            water_liters = 0.20  # default estimation for typical cycle

    event = IrrigationEvent(
        device_id=event_in.device_id,
        start_time=event_in.start_time,
        end_time=event_in.end_time,
        moisture_before=event_in.moisture_before,
        moisture_after=event_in.moisture_after,
        irrigation_mode=event_in.irrigation_mode,
        status=event_in.status,
        estimated_water_liters=water_liters,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    await manager.broadcast({
        "type": "IRRIGATION_EVENT",
        "data": {
            "id": event.id,
            "device_id": event.device_id,
            "start_time": event.start_time.isoformat(),
            "end_time": event.end_time.isoformat() if event.end_time else None,
            "moisture_before": event.moisture_before,
            "moisture_after": event.moisture_after,
            "irrigation_mode": event.irrigation_mode,
            "status": event.status,
            "estimated_water_liters": event.estimated_water_liters,
        }
    })

    return event


@router.get("/history")
def get_irrigation_history(
    device_id: str = DEFAULT_DEVICE_ID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    mode: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Retrieve paginated irrigation history with total summary statistics."""
    query = db.query(IrrigationEvent).filter(IrrigationEvent.device_id == device_id)
    if mode:
        query = query.filter(IrrigationEvent.irrigation_mode == mode.upper())

    total_count = query.count()
    events = (
        query.order_by(IrrigationEvent.start_time.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Calculate total estimated water usage across all events
    total_water = (
        db.query(IrrigationEvent.estimated_water_liters)
        .filter(IrrigationEvent.device_id == device_id)
        .all()
    )
    total_water_sum = round(sum(w[0] for w in total_water if w[0] is not None), 2)

    return {
        "total_count": total_count,
        "total_estimated_water_liters": total_water_sum,
        "limit": limit,
        "offset": offset,
        "events": [
            {
                "id": ev.id,
                "device_id": ev.device_id,
                "start_time": ev.start_time.isoformat(),
                "end_time": ev.end_time.isoformat() if ev.end_time else None,
                "moisture_before": ev.moisture_before,
                "moisture_after": ev.moisture_after,
                "irrigation_mode": ev.irrigation_mode,
                "status": ev.status,
                "estimated_water_liters": ev.estimated_water_liters,
            }
            for ev in events
        ],
    }


@router.get("/history/export")
def export_irrigation_history_csv(
    device_id: str = DEFAULT_DEVICE_ID,
    db: Session = Depends(get_db),
):
    """Generates and downloads a CSV export file of historical irrigation activities."""
    events = (
        db.query(IrrigationEvent)
        .filter(IrrigationEvent.device_id == device_id)
        .order_by(IrrigationEvent.start_time.desc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Event ID",
        "Device ID",
        "Start Time (UTC)",
        "End Time (UTC)",
        "Moisture Before (%)",
        "Moisture After (%)",
        "Irrigation Mode",
        "Status",
        "Estimated Water (Liters) [Calculated based on pump run time @ 1.2 L/min]",
    ])

    for ev in events:
        writer.writerow([
            ev.id,
            ev.device_id,
            ev.start_time.isoformat(),
            ev.end_time.isoformat() if ev.end_time else "N/A",
            f"{ev.moisture_before:.1f}",
            f"{ev.moisture_after:.1f}" if ev.moisture_after is not None else "N/A",
            ev.irrigation_mode,
            ev.status,
            f"{ev.estimated_water_liters:.2f}",
        ])

    csv_data = output.getvalue()
    filename = f"greenpulse_watering_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
