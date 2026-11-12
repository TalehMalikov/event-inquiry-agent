"""Phone notifications (Web Push): "🟡 Mike: Party for 40 · tap to review".

Works with the installable web app on Android, desktop, and iPhone (iPhone: after "Add to Home Screen").
Notifications only go to the devices of the company the email belongs to.
"""
import base64
import json
import logging

from py_vapid import Vapid
from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select

from .config import VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_SUBJECT
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


def notify(subs, *, title: str, body: str, url: str, tag: str = "") -> int:
    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag})
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
