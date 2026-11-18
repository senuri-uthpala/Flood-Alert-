import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..models import Area, Report, User, utcnow
from ..schemas import ReportOut
from ..security import get_current_user, require_admin, require_user
from ..services import maybe_auto_verify

router = APIRouter(prefix="/api/reports", tags=["reports"])

# Verify the real file type from its first bytes - never trust the client's Content-Type/filename.
_MAGIC = {b"\xff\xd8\xff": "jpg", b"\x89PNG\r\n\x1a\n": "png"}


def _image_ext(head: bytes) -> str | None:
    for magic, ext in _MAGIC.items():
        if head.startswith(magic):
            return ext
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def _to_out(r: Report) -> ReportOut:
    out = ReportOut.model_validate(r)
    out.area_name = r.area.name if r.area else None
    out.photo_url = f"/uploads/{r.photo_path}" if r.photo_path else None
    return out


@router.post("", response_model=ReportOut, status_code=201)
async def create_report(
    area_id: int = Form(...),
    type: str = Form(..., pattern="^(flood|landslide)$"),
    description: str | None = Form(None, max_length=500),
    lat: float | None = Form(None, ge=5.5, le=10.2),
    lng: float | None = Form(None, ge=79.3, le=82.1),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),  # login required -> accountability, less spam
):
    if not db.get(Area, area_id):
        raise HTTPException(404, "Area not found")

    recent = db.scalar(select(func.count()).select_from(Report).where(
        Report.user_id == user.id, Report.created_at >= utcnow() - timedelta(hours=1)))
    if recent >= config.REPORTS_PER_HOUR:
        raise HTTPException(429, "Too many reports - try again later")

    photo_name = None
    if photo and photo.filename:
        data = await photo.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
        if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(413, f"Photo too large (max {config.MAX_UPLOAD_MB} MB)")
        ext = _image_ext(data[:16])
        if not ext:
            raise HTTPException(415, "Only JPEG, PNG or WebP photos are allowed")
        photo_name = f"{uuid.uuid4().hex}.{ext}"
        (config.UPLOAD_DIR / photo_name).write_bytes(data)

    report = Report(user_id=user.id, area_id=area_id, type=type, description=description,
                    lat=lat, lng=lng, photo_path=photo_name)
    db.add(report)
    db.flush()
    maybe_auto_verify(db, report)
    db.commit()
    return _to_out(report)


@router.get("", response_model=list[ReportOut])
def list_reports(status: str | None = Query(None, pattern="^(pending|verified|rejected)$"),
                 area_id: int | None = None, limit: int = Query(100, ge=1, le=300),
                 db: Session = Depends(get_db), user: User | None = Depends(get_current_user)):
    """Public sees verified reports only. Admins can filter by any status."""
    is_admin = bool(user and user.role == "admin")
    q = select(Report).order_by(Report.id.desc()).limit(limit)
    if not is_admin:
        q = q.where(Report.status == "verified")
    elif status:
        q = q.where(Report.status == status)
    if area_id:
        q = q.where(Report.area_id == area_id)
    return [_to_out(r) for r in db.scalars(q).all()]


@router.get("/mine", response_model=list[ReportOut])
def my_reports(db: Session = Depends(get_db), user: User = Depends(require_user)):
    rows = db.scalars(select(Report).where(Report.user_id == user.id).order_by(Report.id.desc()).limit(100)).all()
    return [_to_out(r) for r in rows]


@router.post("/{report_id}/{action}", response_model=ReportOut)
def moderate(report_id: int, action: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if action not in ("verify", "reject"):
        raise HTTPException(400, "action must be 'verify' or 'reject'")
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    report.status = "verified" if action == "verify" else "rejected"
    db.commit()
    return _to_out(report)
