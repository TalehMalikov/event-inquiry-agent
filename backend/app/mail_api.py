"""Gmail endpoints: connect/disconnect, push notifications from Google, manual check, and the daily job.

Flow for a new email:
  Gmail -> Pub/Sub -> POST /api/gmail/push -> ingest(): fetch new inbox messages since our saved
  position, skip robots/newsletters, save each once -> process_message() runs the agent.
"""
import base64
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import gmail
from .config import CRON_SECRET, GMAIL_PUSH_TOKEN, MAILBOX_ENCRYPTION_KEY
from .db import Mailbox, Message, SessionLocal, utcnow

log = logging.getLogger("mail")
router = APIRouter(prefix="/api")

# Set by main.setup_mail() (avoids a circular import with main.py)
current = admin = process_message = over_daily_limit = get_graph = None


def setup(**deps):
    globals().update(deps)


def _ms_to_dt(ms):
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc) if ms else None


def status_dict(mb):
    if mb is None:
        return {"connected": False, "configured": gmail.configured()}
    return {"connected": True, "configured": True, "provider": mb.provider, "email": mb.email_address,
            "status": mb.status, "last_error": mb.last_error,
            "last_synced_at": mb.last_synced_at.isoformat() if mb.last_synced_at else None,
            "watch_expires_at": mb.watch_expires_at.isoformat() if mb.watch_expires_at else None}


def _mailbox_of(s, company_id):
    return s.scalar(select(Mailbox).where(Mailbox.company_id == company_id))


# ---------- Ingest: Gmail -> our database ----------

def ingest(mailbox_id: int) -> list[int]:
    """Save new inbox emails for one mailbox and return the ids of those the agent should process.

    The mailbox row is locked for the whole step, so two notifications arriving together can't
    process the same emails twice (and the unique (mailbox, gmail id) key is a second guard)."""
    created = []
    with SessionLocal() as s:
        mb = s.scalar(select(Mailbox).where(Mailbox.id == mailbox_id).with_for_update())
        if mb is None:
            return []
        try:
            try:
                ids, latest = gmail.new_message_ids(mb, mb.history_id)
            except gmail.HistoryTooOld:
                ids, latest = gmail.recent_inbox_ids(mb), gmail.call(mb, "GET", "/profile")["historyId"]
            seen = set(s.scalars(select(Message.external_id).where(Message.mailbox_id == mb.id,
                                                                   Message.external_id.in_(ids)))) if ids else set()
            for gid in ids:
                if gid in seen:
                    continue
                try:
                    e = gmail.fetch(mb, gid)
                except gmail.GmailError as err:
                    if "404" in str(err):  # deleted before we got to it
                        continue
                    raise
                if reason := gmail.skip_reason(e, mb.email_address):
                    log.info("Skipping %s from %s: %s", gid, e["from_email"], reason)
                    continue
                m = Message(company_id=mb.company_id, mailbox_id=mb.id, external_id=e["id"],
                            external_thread_id=e["thread_id"], rfc_message_id=e["rfc_message_id"],
                            email_references=e["references"], reply_to=e["reply_to"] or None,
                            from_name=e["from_name"], from_email=e["from_email"], subject=e["subject"],
                            body=e["body"], thread_id=secrets.token_hex(16), status="processing")
                if over_daily_limit(s, mb.company_id):
                    m.status, m.error = "error", "Daily AI draft limit reached. Use Retry tomorrow."
                s.add(m)
                s.flush()
                if m.status == "processing":
                    created.append(m.id)
            mb.history_id = str(max(int(latest), int(mb.history_id or 0)))
            mb.status, mb.last_error, mb.last_synced_at = "ok", None, utcnow()
            s.commit()
        except gmail.GmailError as err:
            s.rollback()
            with SessionLocal() as s2:
                m2 = s2.get(Mailbox, mailbox_id)
                m2.status, m2.last_error = "error", str(err)[:1000]
                s2.commit()
            log.warning("Ingest failed for mailbox %s: %s", mailbox_id, err)
    return created


def ingest_and_process(mailbox_id: int) -> int:
    ids = ingest(mailbox_id)
    for mid in ids:
        process_message(mid)
    return len(ids)


# ---------- Connect / disconnect (company admins) ----------

def _state_key():
    return "oauth-state:" + MAILBOX_ENCRYPTION_KEY


class CallbackIn(BaseModel):
    code: str = Field(min_length=1, max_length=2000)
    state: str = Field(min_length=1, max_length=2000)


def register(app_router: APIRouter):
    """Attach the endpoints, using main.py's auth dependencies."""

    @app_router.get("/gmail")
    def status(who=Depends(current)):
        with SessionLocal() as s:
            return status_dict(_mailbox_of(s, who.company_id))

    @app_router.post("/gmail/connect")
    def connect(who=Depends(admin)):
        if not gmail.configured():
            raise HTTPException(503, "Gmail isn't set up on the server yet")
        state = jwt.encode({"u": who.ctx.user_id, "o": who.ctx.org_id, "n": secrets.token_urlsafe(8),
                            "exp": int(time.time()) + 900}, _state_key(), algorithm="HS256")
        return {"url": gmail.auth_url(state)}

    @app_router.post("/gmail/callback")
    def callback(body: CallbackIn, who=Depends(admin)):
        # The state proves this sign-in was started by this same user, for this same company (stops CSRF)
        try:
            st = jwt.decode(body.state, _state_key(), algorithms=["HS256"])
        except jwt.PyJWTError:
            raise HTTPException(400, "This Gmail sign-in link expired. Click Connect Gmail again.")
        if st.get("u") != who.ctx.user_id or st.get("o") != who.ctx.org_id:
            raise HTTPException(400, "This Gmail sign-in was started from another account or company.")
        try:
            tokens = gmail.exchange_code(body.code)
            prof = gmail.profile_with_token(tokens["access_token"])
        except gmail.GmailError as e:
            raise HTTPException(400, str(e))
        address = prof["emailAddress"].lower()
        with SessionLocal() as s:
            other = s.scalar(select(Mailbox).where(Mailbox.email_address == address))
            if other and other.company_id != who.company_id:
                raise HTTPException(409, f"{address} is already connected to another company.")
            mb = _mailbox_of(s, who.company_id)
            if mb and mb.email_address != address:
                gmail.stop(mb)
                s.delete(mb)
                s.flush()
                mb = None
            if mb is None:
                mb = Mailbox(company_id=who.company_id, provider="gmail", email_address=address,
                             refresh_token_enc="")
                s.add(mb)
            mb.refresh_token_enc = gmail.encrypt(tokens["refresh_token"])
            s.flush()
            gmail.forget(mb.id)
            try:
                w = gmail.watch(mb)
            except gmail.GmailError as e:
                s.rollback()
                raise HTTPException(502, f"Connected, but Gmail notifications failed: {e}")
            # Start from "now": earlier emails are not answered
            mb.history_id = str(w["historyId"])
            mb.watch_expires_at = _ms_to_dt(w.get("expiration"))
            mb.status, mb.last_error, mb.last_synced_at = "ok", None, utcnow()
            s.commit()
            return status_dict(mb)

    @app_router.delete("/gmail")
    def disconnect(who=Depends(admin)):
        with SessionLocal() as s:
            mb = _mailbox_of(s, who.company_id)
            if mb:
                gmail.stop(mb)
                try:
                    gmail.revoke(gmail.decrypt(mb.refresh_token_enc))
                except Exception:  # noqa: BLE001
                    pass
                gmail.forget(mb.id)
                s.delete(mb)
                s.commit()
        return status_dict(None)

    @app_router.post("/gmail/sync")
    def sync(who=Depends(current)):
        """'Check for new mail' button: same as a push notification, on demand."""
        with SessionLocal() as s:
            mb = _mailbox_of(s, who.company_id)
            if mb is None:
                raise HTTPException(409, "Connect Gmail first")
            mailbox_id = mb.id
        n = ingest_and_process(mailbox_id)
        with SessionLocal() as s:
            return {"new": n, **status_dict(s.get(Mailbox, mailbox_id))}


# ---------- Called by Google and by Vercel (not by users) ----------

@router.post("/gmail/push")
async def push(request: Request, token: str = ""):
    """Pub/Sub push: {"message": {"data": base64('{"emailAddress": ..., "historyId": ...}')}}"""
    if not GMAIL_PUSH_TOKEN or not hmac.compare_digest(token, GMAIL_PUSH_TOKEN):
        raise HTTPException(403, "Forbidden")
    try:
        envelope = await request.json()
        data = json.loads(base64.b64decode(envelope["message"]["data"]))
        address = data["emailAddress"].lower()
    except Exception:  # noqa: BLE001  (malformed: acknowledge so Pub/Sub doesn't retry forever)
        return Response(status_code=204)
    get_graph()
    with SessionLocal() as s:
        mb = s.scalar(select(Mailbox).where(Mailbox.email_address == address))
        mailbox_id = mb.id if mb else None
    if mailbox_id:
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(ingest_and_process, mailbox_id)
    return Response(status_code=204)


@router.get("/cron/gmail")
def cron(request: Request):
    """Daily (Vercel Cron): renew Gmail notifications before their 7-day expiry, and catch any missed mail."""
    if not CRON_SECRET or not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {CRON_SECRET}"):
        raise HTTPException(401, "Unauthorized")
    get_graph()
    renewed, processed = 0, 0
    with SessionLocal() as s:
        ids = list(s.scalars(select(Mailbox.id)))
    for mailbox_id in ids:
        with SessionLocal() as s:
            mb = s.get(Mailbox, mailbox_id)
            if mb.watch_expires_at is None or mb.watch_expires_at < utcnow() + timedelta(days=3):
                try:
                    w = gmail.watch(mb)
                    mb.watch_expires_at = _ms_to_dt(w.get("expiration"))
                    renewed += 1
                except gmail.GmailError as e:
                    mb.status, mb.last_error = "error", str(e)[:1000]
                s.commit()
        processed += ingest_and_process(mailbox_id)
    return {"mailboxes": len(ids), "renewed": renewed, "processed": processed}
