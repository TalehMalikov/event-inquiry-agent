"""Phone notifications (Web Push): "🟡 Mike: Party for 40 · tap to review".

Works with the installable web app on Android, desktop, and iPhone (iPhone: after "Add to Home Screen").
Notifications only go to the devices of the company the email belongs to.
"""
import base64
import json
import logging
import time

import jwt

from py_vapid import Vapid
from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select

from .config import MAILBOX_ENCRYPTION_KEY, VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_SUBJECT
from .db import PushSubscription, SessionLocal

log = logging.getLogger("push")
_vapid = None


def configured():
    return bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)


def _key():
    global _vapid
    if _vapid is None:
        _vapid = Vapid.from_pem(base64.b64decode(VAPID_PRIVATE_KEY))
    return _vapid


def _send(sub: PushSubscription, payload: str) -> bool:
    """True if delivered; False if the device unsubscribed (we then forget it)."""
    try:
        webpush(subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                data=payload, vapid_private_key=_key(), vapid_claims={"sub": VAPID_SUBJECT},
                ttl=12 * 3600, timeout=10)
        return True
    except WebPushException as e:
        status = getattr(e.response, "status_code", None)
        if status in (404, 410):  # expired or the user turned notifications off
            return False
        log.warning("Push failed (%s): %s", status, e)
        return True
    except Exception as e:  # noqa: BLE001  (a ping must never break the email flow)
        log.warning("Push failed: %s", e)
        return True


# ---------- Send / Decline buttons on the notification ----------
# The buttons work without the app open, so each ping carries a one-time key for that ONE email and
# action. Web Push payloads are end-to-end encrypted to the device; the key expires after 48 hours and
# only works while the email is still waiting.
ACTION_TTL = 48 * 3600


def _action_secret():
    return "push-action:" + MAILBOX_ENCRYPTION_KEY


def action_token(message_id: int, action: str) -> str:
    return jwt.encode({"m": message_id, "a": action, "exp": int(time.time()) + ACTION_TTL},
                      _action_secret(), algorithm="HS256")


def read_action_token(token: str):
    """(message_id, action) or None if the key is forged or expired."""
    try:
        d = jwt.decode(token, _action_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if d.get("a") not in ("approve", "reject"):
        return None
    return int(d["m"]), d["a"]


def notify(subs, *, title: str, url: str, tag: str = "", body: str = "", actions=None) -> int:
    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag, "actions": actions or []})
    gone, sent = [], 0
    for sub in subs:
        if _send(sub, payload):
            sent += 1
        else:
            gone.append(sub.id)
    if gone:
        with SessionLocal() as s:
            s.execute(delete(PushSubscription).where(PushSubscription.id.in_(gone)))
            s.commit()
    return sent


def notify_company(company_id: int, **msg) -> int:
    if not configured():
        return 0
    with SessionLocal() as s:
        subs = list(s.scalars(select(PushSubscription).where(PushSubscription.company_id == company_id)))
    return notify(subs, **msg)
