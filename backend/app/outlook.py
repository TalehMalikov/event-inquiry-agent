"""Outlook connection (Microsoft Graph): the same jobs as gmail.py, for Outlook.com and Microsoft 365 inboxes.

Connect (OAuth), learn about new mail, read it, put drafts + colored categories in the owner's Outlook, send replies.
Works for personal accounts (outlook.com, hotmail.com) and work/school accounts whose admin allows the app.

Differences from Gmail that matter here:
- Ids: we ask for "immutable" ids, so a message keeps its id when it moves folders (draft -> Sent Items).
- Replies: Outlook's own createReply makes the draft, so threading and the To address are handled by Outlook.
- New mail: we check the Inbox and Sent Items for anything newer than our saved position (no history log).
- Colors: Outlook "categories" (green/yellow/red), the same three names as the Gmail labels.
"""
import json
import logging
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from . import gmail  # shared helpers: encryption, quote stripping, robot filter, reply HTML
from .config import APP_URL, MAILBOX_ENCRYPTION_KEY, MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET
from .mailbase import MailError

log = logging.getLogger("outlook")

NAME = "Outlook"
SCOPES = ["offline_access", "User.Read", "Mail.ReadWrite", "Mail.Send", "MailboxSettings.ReadWrite"]
NEEDED = {"mail.readwrite", "mail.send"}  # without these we can't work; categories are a bonus
AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
API = "https://graph.microsoft.com/v1.0"
# Outlook's preset colors: preset4 = green, preset3 = yellow, preset0 = red
CATEGORIES = {"green": ("AI · Sent", "preset4"), "yellow": ("AI · Needs approval", "preset3"),
              "red": ("AI · Needs you", "preset0")}
FOLDERS = (("in", "inbox", "receivedDateTime"), ("sent", "sentitems", "sentDateTime"))
PAGE = 50


class OutlookError(MailError):
    pass


def configured():
    return bool(MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET and MAILBOX_ENCRYPTION_KEY)


def push_enabled():
    return False  # checked on a schedule (like Gmail without Pub/Sub); Graph webhooks can come later


def can_draft(mailbox) -> bool:
    return True  # Mail.ReadWrite is always part of the Outlook connection


def _req(method, url, **kw):
    """Every network call goes through here (tests replace it with a fake Microsoft)."""
    return httpx.request(method, url, timeout=20, **kw)


# ---------- OAuth: "Connect Outlook" ----------

def redirect_uri():
    return f"{APP_URL}/outlook/callback"


def auth_url(state: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_id": MICROSOFT_CLIENT_ID, "response_type": "code", "redirect_uri": redirect_uri(),
        "response_mode": "query", "scope": " ".join(SCOPES), "state": state,
        "prompt": "select_account",  # lets the owner pick which Microsoft account to connect
    })


def _granted(tokens) -> set:
    return {s.rsplit("/", 1)[-1].lower() for s in tokens.get("scope", "").split()}


def exchange_code(code: str) -> dict:
    r = _req("POST", TOKEN_URL, data={
        "client_id": MICROSOFT_CLIENT_ID, "client_secret": MICROSOFT_CLIENT_SECRET, "code": code,
        "redirect_uri": redirect_uri(), "grant_type": "authorization_code", "scope": " ".join(SCOPES)})
    if r.status_code != 200:
        raise OutlookError(f"Microsoft rejected the sign-in: {r.text[:300]}")
    tokens = r.json()
    if missing := NEEDED - _granted(tokens):
        raise OutlookError(f"Please allow all requested Outlook permissions (missing: {', '.join(sorted(missing))})")
    if not tokens.get("refresh_token"):
        raise OutlookError("Microsoft did not return a long-lived token. Connect Outlook again.")
    return tokens


def connect_profile(tokens) -> tuple[str, str]:
    """(email address, starting position = now: older emails are not answered)."""
    r = _req("GET", API + "/me?$select=mail,userPrincipalName",
             headers={"Authorization": f"Bearer {tokens['access_token']}"})
    if r.status_code != 200:
        raise OutlookError(f"Could not read the Outlook account ({r.status_code})")
    me = r.json()
    address = (me.get("mail") or me.get("userPrincipalName") or "").lower()
    if "@" not in address:
        raise OutlookError("This Microsoft account has no mailbox.")
    return address, _new_cursor()


def scopes_of(tokens) -> str:
    return tokens.get("scope", "")


def revoke(refresh_token: str):
    pass  # Microsoft has no per-token revoke; owners remove the app at account.live.com/consent/Manage


def stop(mailbox):
    pass  # nothing to switch off: we only check on a schedule


# ---------- Access tokens ----------

_access_cache: dict[int, tuple[str, float]] = {}
_cache_lock = threading.Lock()


def access_token(mailbox) -> str:
    with _cache_lock:
        hit = _access_cache.get(mailbox.id)
        if hit and hit[1] > time.time() + 60:
            return hit[0]
    r = _req("POST", TOKEN_URL, data={
        "client_id": MICROSOFT_CLIENT_ID, "client_secret": MICROSOFT_CLIENT_SECRET, "grant_type": "refresh_token",
        "refresh_token": gmail.decrypt(mailbox.refresh_token_enc), "scope": " ".join(SCOPES)})
    if r.status_code != 200:
        raise OutlookError(f"Outlook connection expired or was revoked. Reconnect Outlook in Settings. ({r.status_code})")
    d = r.json()
    if d.get("refresh_token"):
        # Microsoft hands out a fresh refresh token each time; the caller's database session saves it
        mailbox.refresh_token_enc = gmail.encrypt(d["refresh_token"])
    with _cache_lock:
        _access_cache[mailbox.id] = (d["access_token"], time.time() + int(d.get("expires_in", 3600)))
    return d["access_token"]


def forget(mailbox_id: int):
    with _cache_lock:
        _access_cache.pop(mailbox_id, None)


def call(mailbox, method, path, *, text_body=False, **kw) -> dict:
    prefer = 'IdType="ImmutableId"' + (', outlook.body-content-type="text"' if text_body else "")
    headers = {"Authorization": f"Bearer {access_token(mailbox)}", "Prefer": prefer}
    r = _req(method, API + path, headers=headers, **kw)
    if r.status_code >= 400:
        raise OutlookError(f"Outlook {method} {path.split('?')[0]} failed ({r.status_code}): {r.text[:300]}")
    return r.json() if r.content else {}


# ---------- New mail ----------

def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_cursor() -> str:
    now = _now()
    return json.dumps({k: {"t": now, "ids": []} for k, _, _ in FOLDERS})


def poll(mailbox) -> tuple[list, str]:
    """Ids of new Inbox mail and new Sent Items (the owner's replies) since our saved position, and the new position.

    The position is the newest timestamp seen per folder, plus the ids at exactly that second, so the next check
    neither misses an email that arrived in the same second nor processes one twice."""
    try:
        cur = json.loads(mailbox.history_id or "")
    except ValueError:
        cur = json.loads(_new_cursor())
    ids = []
    for key, folder, field in FOLDERS:
        pos = cur.get(key) or {"t": _now(), "ids": []}
        since, at_since = pos["t"], list(pos["ids"])
        d = call(mailbox, "GET", f"/me/mailFolders/{folder}/messages?" + urlencode({
            "$filter": f"{field} ge {since}", "$orderby": f"{field} asc", "$select": f"id,{field}", "$top": PAGE}))
        for m in d.get("value", []):
            t = m.get(field) or since
            if t == since and m["id"] in at_since:
                continue
            if m["id"] not in ids:
                ids.append(m["id"])
            if t > since:
                since, at_since = t, [m["id"]]
            elif t == since:
                at_since.append(m["id"])
        cur[key] = {"t": since, "ids": at_since[-PAGE:]}
    return ids, json.dumps(cur)


# ---------- Reading one email ----------

def _address(x) -> tuple[str, str]:
    e = (x or {}).get("emailAddress") or {}
    return e.get("name") or "", (e.get("address") or "").lower()


def fetch(mailbox, message_id: str) -> dict:
    m = call(mailbox, "GET", f"/me/messages/{message_id}?$select=id,conversationId,internetMessageId,subject,from,"
                             "replyTo,body,internetMessageHeaders,isDraft", text_body=True)
    headers = {h["name"].lower(): h["value"] for h in (m.get("internetMessageHeaders") or [])}
    from_name, from_email = _address(m.get("from"))
    reply_to = [_address(r)[1] for r in (m.get("replyTo") or []) if _address(r)[1]]
    labels = ["INBOX"]
    if from_email == mailbox.email_address.lower():
        labels = ["SENT"]  # sent by the owner: same meaning as Gmail's SENT label
    if m.get("isDraft"):
        labels.append("DRAFT")
    body = gmail.strip_quoted((m.get("body") or {}).get("content") or "")[:gmail.MAX_BODY]
    return {
        "id": m["id"], "thread_id": m.get("conversationId"), "labels": labels, "headers": headers,
        "from_name": (from_name or from_email.split("@")[0])[:200], "from_email": from_email[:320],
        "reply_to": (reply_to[0] if reply_to else "")[:320], "subject": (m.get("subject") or "(no subject)")[:500],
        "rfc_message_id": (m.get("internetMessageId") or "")[:998], "references": headers.get("references", ""),
        "body": body or "(empty email)",
    }


skip_reason = gmail.skip_reason


# ---------- Drafts and replies ----------

def _is_draft(mailbox, message_id) -> bool:
    try:
        return bool(call(mailbox, "GET", f"/me/messages/{message_id}?$select=isDraft").get("isDraft"))
    except OutlookError as e:
        if "(404)" in str(e):
            return False
        raise


def _reply_draft(mailbox, reply_to_id, to, body) -> str:
    """Outlook's own reply draft (keeps the thread), with our text as the whole body."""
    if not reply_to_id:
        raise OutlookError("The original email is missing, so the reply can't be threaded.")
    draft_id = call(mailbox, "POST", f"/me/messages/{reply_to_id}/createReply", json={})["id"]
    call(mailbox, "PATCH", f"/me/messages/{draft_id}", json={
        "body": {"contentType": "HTML", "content": gmail.to_html(body)},
        "toRecipients": [{"emailAddress": {"address": to}}]})
    return draft_id


def create_draft(mailbox, *, to, body, reply_to_id=None, **_) -> str:
    return _reply_draft(mailbox, reply_to_id, to, body)


def send_reply(mailbox, *, to, body, reply_to_id=None, draft_id=None, **_) -> dict:
    """Send in the thread. If our draft is still there, send that one (updated to the final text), so Outlook
    doesn't keep a stale copy."""
    if draft_id and _is_draft(mailbox, draft_id):
        call(mailbox, "PATCH", f"/me/messages/{draft_id}", json={
            "body": {"contentType": "HTML", "content": gmail.to_html(body)},
            "toRecipients": [{"emailAddress": {"address": to}}]})
        mid, used = draft_id, True
    else:
        mid, used = _reply_draft(mailbox, reply_to_id, to, body), False
    call(mailbox, "POST", f"/me/messages/{mid}/send")
    return {"id": mid, "used_draft": used}  # immutable id: the same id now points at the sent message


def delete_draft(mailbox, draft_id: str):
    """Remove our draft. Checked first: if the owner already sent it, the id now points at their SENT mail,
    which must never be deleted."""
    try:
        if _is_draft(mailbox, draft_id):
            call(mailbox, "DELETE", f"/me/messages/{draft_id}")
    except OutlookError as e:
        log.warning("Could not delete draft %s: %s", draft_id, e)


# ---------- Colored categories ----------

def ensure_labels(mailbox) -> dict:
    """Our three colored categories exist in the owner's Outlook; returns {"green"|"yellow"|"red": name}."""
    existing = {c["displayName"] for c in call(mailbox, "GET", "/me/outlook/masterCategories").get("value", [])}
    for name, preset in CATEGORIES.values():
        if name not in existing:
            call(mailbox, "POST", "/me/outlook/masterCategories", json={"displayName": name, "color": preset})
    return {color: name for color, (name, _) in CATEGORIES.items()}


def set_color_label(mailbox, label_ids: dict, message_id: str, color):
    """Exactly one of our categories on the email (or none). The owner's own categories are kept."""
    try:
        cats = call(mailbox, "GET", f"/me/messages/{message_id}?$select=categories").get("categories") or []
    except OutlookError as e:
        if "(404)" in str(e):
            return
        raise
    ours = set(label_ids.values())
    new = [c for c in cats if c not in ours] + ([label_ids[color]] if color in label_ids else [])
    if new != cats:
        call(mailbox, "PATCH", f"/me/messages/{message_id}", json={"categories": new})
