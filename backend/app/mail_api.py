"""Mailbox endpoints (Gmail or Outlook): connect/disconnect, push notifications from Google, manual check, the
scheduled job. Provider details live in gmail.py / outlook.py; this file only uses their shared functions.

Flow for a new email (push when Pub/Sub is configured, otherwise the scheduled check / "Check now"):
  Gmail -> Pub/Sub -> POST /api/gmail/push (or GET /api/cron/gmail) -> ingest(): fetch new inbox messages since our saved
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

from . import gmail, providers
from .config import CRON_SECRET, GMAIL_PUSH_TOKEN, MAILBOX_ENCRYPTION_KEY
from .db import Mailbox, Message, SessionLocal, utcnow
from .mailbase import MailError

log = logging.getLogger("mail")
router = APIRouter(prefix="/api")

# Set by main.setup_mail() (avoids a circular import with main.py)
current = admin = process_message = over_daily_limit = get_graph = resume_message = None


def setup(**deps):
    globals().update(deps)


def _ms_to_dt(ms):
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc) if ms else None


def status_dict(mb):
    available = {name: p.configured() for name, p in providers.PROVIDERS.items()}
    if mb is None:
        return {"connected": False, "configured": any(available.values()), "available": available,
                "instant": False}
    prov = providers.of(mb)
    return {"connected": True, "configured": True, "available": available, "provider": mb.provider,
            "provider_name": prov.NAME, "email": mb.email_address,
            "status": mb.status, "last_error": mb.last_error,
            "last_synced_at": mb.last_synced_at.isoformat() if mb.last_synced_at else None,
            "watch_expires_at": mb.watch_expires_at.isoformat() if mb.watch_expires_at else None,
            "instant": prov.push_enabled(), "can_draft": prov.can_draft(mb)}


def _mailbox_of(s, company_id):
    return s.scalar(select(Mailbox).where(Mailbox.company_id == company_id))


# ---------- Ingest: the mailbox -> our database ----------

def ingest(mailbox_id: int):
    """Save new inbox emails for one mailbox. Returns (ids the agent should process,
    [(waiting message id, text)] for replies the owner sent from Gmail).

    The mailbox row is locked for the whole step, so two notifications arriving together can't
    process the same emails twice (and the unique (mailbox, gmail id) key is a second guard)."""
    created, owner_sent = [], []
    with SessionLocal() as s:
        mb = s.scalar(select(Mailbox).where(Mailbox.id == mailbox_id).with_for_update())
        if mb is None:
            return [], []
        prov = providers.of(mb)
        try:
            ids, cursor = prov.poll(mb)
            seen = set(s.scalars(select(Message.external_id).where(Message.mailbox_id == mb.id,
                                                                   Message.external_id.in_(ids)))) if ids else set()
            ours = set(s.scalars(select(Message.sent_external_id).where(Message.mailbox_id == mb.id,
                                                                        Message.sent_external_id.in_(ids)))) if ids else set()
            for gid in ids:
                if gid in seen or gid in ours:
                    continue
                try:
                    e = prov.fetch(mb, gid)
                except MailError as err:
                    if "404" in str(err):  # deleted before we got to it
                        continue
                    raise
                if "SENT" in e["labels"]:
                    # The owner replied from their mailbox (e.g. pressed Send on our draft) in a thread that waits
                    w = s.scalar(select(Message).where(Message.mailbox_id == mb.id, Message.status == "waiting",
                                                       Message.external_thread_id == e["thread_id"])
                                 .order_by(Message.id.desc()).limit(1))
                    if w is not None:
                        owner_sent.append((w.id, e["body"]))
                    continue
                if reason := prov.skip_reason(e, mb.email_address):
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
            mb.history_id = cursor
            mb.status, mb.last_error, mb.last_synced_at = "ok", None, utcnow()
            s.commit()
        except MailError as err:
            s.rollback()
            with SessionLocal() as s2:
                m2 = s2.get(Mailbox, mailbox_id)
                m2.status, m2.last_error = "error", str(err)[:1000]
                s2.commit()
            log.warning("Ingest failed for mailbox %s: %s", mailbox_id, err)
    return created, owner_sent


def ingest_and_process(mailbox_id: int) -> int:
    ids, owner_sent = ingest(mailbox_id)
    for message_id, text in owner_sent:
        try:
            resume_message(message_id, {"action": "sent_in_gmail", "text": text})
        except HTTPException:
            pass  # already handled in the app meanwhile
    for mid in ids:
        process_message(mid)
    return len(ids) + len(owner_sent)


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
    def connect(provider: str = "gmail", who=Depends(admin)):
        """Start connecting the company inbox. provider = gmail | outlook."""
        if provider not in providers.PROVIDERS:
            raise HTTPException(400, "Unknown mail provider")
        prov = providers.get(provider)
        if not prov.configured():
            raise HTTPException(503, f"{prov.NAME} isn't set up on the server yet")
        state = jwt.encode({"u": who.ctx.user_id, "o": who.ctx.org_id, "p": provider, "n": secrets.token_urlsafe(8),
                            "exp": int(time.time()) + 900}, _state_key(), algorithm="HS256")
        return {"url": prov.auth_url(state)}

    @app_router.post("/gmail/callback")
    def callback(body: CallbackIn, who=Depends(admin)):
        # The state proves this sign-in was started by this same user, for this same company (stops CSRF)
        try:
            st = jwt.decode(body.state, _state_key(), algorithms=["HS256"])
        except jwt.PyJWTError:
            raise HTTPException(400, "This sign-in link expired. Click Connect again.")
        if st.get("u") != who.ctx.user_id or st.get("o") != who.ctx.org_id:
            raise HTTPException(400, "This sign-in was started from another account or company.")
        provider = st.get("p", "gmail")
        if provider not in providers.PROVIDERS:
            raise HTTPException(400, "Unknown mail provider")
        prov = providers.get(provider)
        try:
            tokens = prov.exchange_code(body.code)
            address, cursor = prov.connect_profile(tokens)
        except MailError as e:
            raise HTTPException(400, str(e))
        with SessionLocal() as s:
            other = s.scalar(select(Mailbox).where(Mailbox.email_address == address))
            if other and other.company_id != who.company_id:
                raise HTTPException(409, f"{address} is already connected to another company.")
            mb = _mailbox_of(s, who.company_id)
            if mb and (mb.email_address != address or mb.provider != provider):
                providers.of(mb).stop(mb)
                s.delete(mb)
                s.flush()
                mb = None
            if mb is None:
                mb = Mailbox(company_id=who.company_id, provider=provider, email_address=address,
                             refresh_token_enc="")
                s.add(mb)
            mb.refresh_token_enc = gmail.encrypt(tokens["refresh_token"])
            mb.scopes = prov.scopes_of(tokens)
            mb.label_ids = None  # re-check our colored labels on the next use
            s.flush()
            prov.forget(mb.id)
            # Start from "now": earlier emails are not answered
            if provider == "gmail" and gmail.push_enabled():
                try:
                    w = gmail.watch(mb)
                except gmail.GmailError as e:
                    s.rollback()
                    raise HTTPException(502, f"Connected, but Gmail notifications failed: {e}")
                mb.history_id = str(w["historyId"])
                mb.watch_expires_at = _ms_to_dt(w.get("expiration"))
            else:  # no push: the scheduled check picks up mail from this point on
                mb.history_id = cursor
                mb.watch_expires_at = None
            mb.status, mb.last_error, mb.last_synced_at = "ok", None, utcnow()
            s.commit()
            return status_dict(mb)

    @app_router.delete("/gmail")
    def disconnect(who=Depends(admin)):
        with SessionLocal() as s:
            mb = _mailbox_of(s, who.company_id)
            if mb:
                prov = providers.of(mb)
                prov.stop(mb)
                try:
                    prov.revoke(gmail.decrypt(mb.refresh_token_enc))
                except Exception:  # noqa: BLE001
                    pass
                prov.forget(mb.id)
                s.delete(mb)
                s.commit()
        return status_dict(None)

    @app_router.post("/gmail/sync")
    def sync(who=Depends(current)):
        """'Check for new mail' button: same as a push notification, on demand."""
        with SessionLocal() as s:
            mb = _mailbox_of(s, who.company_id)
            if mb is None:
                raise HTTPException(409, "Connect your inbox first")
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
        mb = s.scalar(select(Mailbox).where(Mailbox.email_address == address, Mailbox.provider == "gmail"))
        mailbox_id = mb.id if mb else None
    if mailbox_id:
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(ingest_and_process, mailbox_id)
    return Response(status_code=204)


@router.get("/cron/gmail")
def cron(request: Request):
    """Scheduled check (cron-job.org every 15 min, Vercel Cron daily as backup): fetch new mail for every
    mailbox, and (when push is on) renew Gmail notifications before their 7-day expiry."""
    if not CRON_SECRET or not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {CRON_SECRET}"):
        raise HTTPException(401, "Unauthorized")
    get_graph()
    renewed, processed = 0, 0
    with SessionLocal() as s:
        ids = list(s.scalars(select(Mailbox.id)))
    for mailbox_id in ids:
        with SessionLocal() as s:
            mb = s.get(Mailbox, mailbox_id)
            if mb.provider == "gmail" and gmail.push_enabled() and (mb.watch_expires_at is None
                                         or mb.watch_expires_at < utcnow() + timedelta(days=3)):
                try:
                    w = gmail.watch(mb)
                    mb.watch_expires_at = _ms_to_dt(w.get("expiration"))
                    renewed += 1
                except MailError as e:
                    mb.status, mb.last_error = "error", str(e)[:1000]
                s.commit()
        processed += ingest_and_process(mailbox_id)
    return {"mailboxes": len(ids), "renewed": renewed, "processed": processed}
