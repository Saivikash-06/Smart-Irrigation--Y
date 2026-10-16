from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Alert, utcnow
from ..schemas import AlertResponse
from ..services import DEFAULT_DEVICE_ID
from ..websocket_manager import manager

router = APIRouter(prefix="/api/alerts", tags=["Alerts and Notifications"])


@router.get("", response_model=List[AlertResponse])
def get_alerts(
    device_id: str = DEFAULT_DEVICE_ID,
    unresolved_only: bool = False,
    severity: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Retrieve system alerts with optional severity and un-resolved filters."""
    query = db.query(Alert).filter(Alert.device_id == device_id)
    if unresolved_only:
        query = query.filter(Alert.resolved_at.is_(None))
    if severity:
        query = query.filter(Alert.severity == severity.lower())

    alerts = query.order_by(Alert.created_at.desc()).limit(limit).all()
    return alerts


@router.put("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    """Mark an active alert as resolved."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.resolved_at = utcnow()
    db.commit()
    db.refresh(alert)

    await manager.broadcast({
        "type": "ALERT_RESOLVED",
        "data": {
            "alert_id": alert.id,
            "device_id": alert.device_id,
            "resolved_at": alert.resolved_at.isoformat(),
        }
    })

    return alert
