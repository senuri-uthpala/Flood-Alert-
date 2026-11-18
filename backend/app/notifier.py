"""Alert delivery. Each channel is optional: without credentials it just logs, so the system is
demo-able offline and never crashes because a provider is missing.

  sms   -> Twilio REST API (TWILIO_SID / TWILIO_TOKEN / TWILIO_FROM)
  email -> SMTP (SMTP_HOST / SMTP_USER / SMTP_PASSWORD)
  push  -> Firebase Cloud Messaging via firebase-admin (GOOGLE_APPLICATION_CREDENTIALS), contact = FCM token
In addition, the web app polls /api/alerts and shows browser notifications (no provider needed).
"""
import logging
import smtplib
from email.message import EmailMessage

import httpx

from . import config

log = logging.getLogger("floodalert.notifier")


def _send_sms(to: str, text: str) -> bool:
    if not (config.TWILIO_SID and config.TWILIO_TOKEN and config.TWILIO_FROM):
        return False
    r = httpx.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{config.TWILIO_SID}/Messages.json",
        auth=(config.TWILIO_SID, config.TWILIO_TOKEN),
        data={"To": to, "From": config.TWILIO_FROM, "Body": text},
        timeout=15,
    )
    r.raise_for_status()
    return True


def _send_email(to: str, text: str) -> bool:
    if not (config.SMTP_HOST and config.SMTP_USER and config.SMTP_PASSWORD):
        return False
    msg = EmailMessage()
    msg["Subject"] = "FloodAlert LK warning"
    msg["From"], msg["To"] = config.SMTP_FROM, to
    msg.set_content(text)
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as s:
        s.starttls()
        s.login(config.SMTP_USER, config.SMTP_PASSWORD)
        s.send_message(msg)
    return True


def _send_push(token: str, text: str) -> bool:
    if not config.FIREBASE_CREDENTIALS:
        return False
    import firebase_admin  # optional dependency
    from firebase_admin import messaging

    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    messaging.send(messaging.Message(notification=messaging.Notification(title="FloodAlert LK", body=text), token=token))
    return True


_SENDERS = {"sms": _send_sms, "email": _send_email, "push": _send_push}


def notify(channel: str, contact: str, text: str) -> bool:
    """Returns True if a real provider delivered it; otherwise logs and returns False."""
    try:
        if _SENDERS[channel](contact, text):
            return True
    except Exception as exc:
        log.error("Notification via %s failed: %s", channel, exc)
    log.info("[ALERT %s -> %s] %s", channel, contact, text)
    return False
