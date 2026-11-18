import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Area, Subscription, User
from ..schemas import SubscriptionIn, SubscriptionOut
from ..security import require_user

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])

MAX_SUBSCRIPTIONS_PER_USER = 10
_PHONE = re.compile(r"^\+?[0-9]{9,15}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.post("", response_model=SubscriptionOut, status_code=201)
def subscribe(body: SubscriptionIn, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not db.get(Area, body.area_id):
        raise HTTPException(404, "Area not found")
    contact = body.contact.strip()
    if body.channel == "sms" and not _PHONE.match(contact.replace(" ", "")):
        raise HTTPException(422, "Enter a valid phone number, e.g. +94771234567")
    if body.channel == "email" and not _EMAIL.match(contact):
        raise HTTPException(422, "Enter a valid email address")

    # each user manages only their OWN subscriptions (never touch another user's row)
    existing = db.scalar(select(Subscription).where(
        Subscription.user_id == user.id, Subscription.area_id == body.area_id,
        Subscription.contact == contact, Subscription.channel == body.channel))
    if not existing:
        count = db.scalar(select(func.count()).select_from(Subscription).where(Subscription.user_id == user.id))
        if count >= MAX_SUBSCRIPTIONS_PER_USER:
            raise HTTPException(429, f"Subscription limit reached ({MAX_SUBSCRIPTIONS_PER_USER})")
    if existing:
        existing.language = body.language
        sub = existing
    else:
        sub = Subscription(user_id=user.id, area_id=body.area_id, contact=contact,
                           channel=body.channel, language=body.language)
        db.add(sub)
    db.commit()
    return sub


@router.get("", response_model=list[SubscriptionOut])
def my_subscriptions(db: Session = Depends(get_db), user: User = Depends(require_user)):
    return db.scalars(select(Subscription).where(Subscription.user_id == user.id)).all()


@router.delete("/{sub_id}", status_code=204)
def unsubscribe(sub_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    sub = db.get(Subscription, sub_id)
    if not sub or sub.user_id != user.id:
        raise HTTPException(404, "Subscription not found")
    db.delete(sub)
    db.commit()
