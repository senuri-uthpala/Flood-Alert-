from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import ml
from ..database import get_db
from ..models import Alert, Area, Report, Subscription, User
from ..schemas import AlertOut, BroadcastIn
from ..security import require_admin
from ..services import dispatch_alert, refresh_all

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("/refresh")
def refresh(db: Session = Depends(get_db)):
    """Manually trigger the same job the scheduler runs."""
    return refresh_all(db)


@router.post("/broadcast", response_model=AlertOut, status_code=201)
def broadcast(body: BroadcastIn, db: Session = Depends(get_db)):
    area = db.get(Area, body.area_id)
    if not area:
        raise HTTPException(404, "Area not found")
    alert = dispatch_alert(db, area, body.level, manual=True, custom=body.message)
    db.commit()
    return AlertOut.model_validate(alert).model_copy(update={"area_name": area.name})


@router.post("/reload-model")
def reload_model():
    return {"model_loaded": ml.reload_model()}


@router.get("/stats")
def admin_stats(db: Session = Depends(get_db)):
    reports_by_status = dict(db.execute(select(Report.status, func.count()).group_by(Report.status)).all())
    return {
        "users": db.scalar(select(func.count()).select_from(User)),
        "subscriptions": db.scalar(select(func.count()).select_from(Subscription)),
        "alerts_sent": db.scalar(select(func.count()).select_from(Alert)),
        "reports": {k: reports_by_status.get(k, 0) for k in ("pending", "verified", "rejected")},
    }
