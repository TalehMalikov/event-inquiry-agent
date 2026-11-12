"""Gmail connection: connect (OAuth), learn about new mail (Pub/Sub push + history), read, reply.

Plain REST calls (httpx) instead of Google's heavy client libraries, to keep the serverless bundle small.
Scopes: read + send only. The app can never delete or change the owner's mail.
"""
import base64
import html
import logging
import re
import threading
import time
from email.message import EmailMessage
from email.utils import getaddresses, make_msgid, parseaddr
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet

from .config import (APP_URL, GMAIL_PUBSUB_TOPIC, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_PROJECT_ID,
                     MAILBOX_ENCRYPTION_KEY)

log = logging.getLogger("gmail")

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send"]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
MAX_BODY = 20000


class GmailError(Exception):
    pass


class HistoryTooOld(GmailError):
    """Our saved position is older than Gmail keeps history for (about a week)."""


def push_enabled():
    return bool(GMAIL_PUBSUB_TOPIC)


def configured():
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_PROJECT_ID and MAILBOX_ENCRYPTION_KEY)


# ---------- Encrypting stored tokens ----------

def _fernet():
    return Fernet(MAILBOX_ENCRYPTION_KEY.encode())


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


# ---------- OAuth: "Connect Gmail" ----------

def redirect_uri():
    return f"{APP_URL}/gmail/callback"


def auth_url(state: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_id": GOOGLE_CLIENT_ID, "redirect_uri": redirect_uri(), "response_type": "code",
        "scope": " ".join(SCOPES), "access_type": "offline",  # offline: get a refresh token
        "prompt": "consent",  # always return a refresh token, even on reconnect
        "include_granted_scopes": "true", "state": state,
    })


def exchange_code(code: str) -> dict:
    r = httpx.post(TOKEN_URL, data={
        "code": code, "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri(), "grant_type": "authorization_code"}, timeout=15)
    if r.status_code != 200:
        raise GmailError(f"Google rejected the sign-in: {r.text[:300]}")
    tokens = r.json()
    granted = set(tokens.get("scope", "").split())
    missing = [s.rsplit("/", 1)[-1] for s in SCOPES if s not in granted]
    if missing:
        raise GmailError(f"Please allow all requested Gmail permissions (missing: {', '.join(missing)})")
    if not tokens.get("refresh_token"):
        raise GmailError("Google did not return a long-lived token. Remove the app at "
                         "myaccount.google.com/permissions and connect again.")
    return tokens


def revoke(refresh_token: str):
    try:
        httpx.post(REVOKE_URL, data={"token": refresh_token}, timeout=10)
    except Exception as e:  # noqa: BLE001
        log.warning("Token revoke failed: %s", e)


# ---------- Access tokens (short-lived, refreshed from the stored refresh token) ----------

_access_cache: dict[int, tuple[str, float]] = {}
_cache_lock = threading.Lock()


def access_token(mailbox) -> str:
    with _cache_lock:
        hit = _access_cache.get(mailbox.id)
        if hit and hit[1] > time.time() + 60:
            return hit[0]
    r = httpx.post(TOKEN_URL, data={
        "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
        "refresh_token": decrypt(mailbox.refresh_token_enc), "grant_type": "refresh_token"}, timeout=15)
    if r.status_code != 200:
        raise GmailError("Gmail connection expired or was revoked. Reconnect Gmail in Settings. "
                         f"({r.json().get('error', r.status_code) if r.headers.get('content-type', '').startswith('application/json') else r.status_code})")
    d = r.json()
    with _cache_lock:
        _access_cache[mailbox.id] = (d["access_token"], time.time() + d.get("expires_in", 3600))
    return d["access_token"]


def forget(mailbox_id: int):
    with _cache_lock:
        _access_cache.pop(mailbox_id, None)


def _call(token: str, method: str, path: str, **kw) -> dict:
    r = httpx.request(method, API + path, headers={"Authorization": f"Bearer {token}"}, timeout=20, **kw)
    if r.status_code == 404 and path.startswith("/history"):
        raise HistoryTooOld(path)
    if r.status_code >= 400:
        raise GmailError(f"Gmail {method} {path.split('?')[0]} failed ({r.status_code}): {r.text[:300]}")
    return r.json() if r.content else {}


def call(mailbox, method, path, **kw):
    return _call(access_token(mailbox), method, path, **kw)


def profile_with_token(token: str) -> dict:
    return _call(token, "GET", "/profile")


# ---------- Notifications ----------

def watch(mailbox) -> dict:
    """Ask Gmail to notify our Pub/Sub topic about INBOX changes. Lasts 7 days; the daily job renews it."""
    return call(mailbox, "POST", "/watch", json={
        "topicName": f"projects/{GOOGLE_PROJECT_ID}/topics/{GMAIL_PUBSUB_TOPIC}",
        "labelIds": ["INBOX"], "labelFilterBehavior": "INCLUDE"})


def stop(mailbox):
    try:
        call(mailbox, "POST", "/stop")
    except Exception as e:  # noqa: BLE001
        log.warning("Gmail stop failed: %s", e)


def new_message_ids(mailbox, start_history_id: str):
    """Ids of messages added to the INBOX since start_history_id, and the newest history id."""
    ids, page, latest = [], None, start_history_id
    while True:
        params = {"startHistoryId": start_history_id, "historyTypes": "messageAdded", "labelId": "INBOX",
                  "maxResults": 100}
        if page:
            params["pageToken"] = page
        d = call(mailbox, "GET", "/history?" + urlencode(params))
        latest = d.get("historyId", latest)
        for h in d.get("history", []):
            for added in h.get("messagesAdded", []):
                mid = added["message"]["id"]
                if mid not in ids:
                    ids.append(mid)
        page = d.get("nextPageToken")
        if not page or len(ids) >= 200:
            return ids, latest


def recent_inbox_ids(mailbox, limit=10):
    """Fallback when history is too old: the newest inbox messages from the last day."""
    d = call(mailbox, "GET", "/messages?" + urlencode({"labelIds": "INBOX", "q": "newer_than:1d",
                                                        "maxResults": limit}))
    return [m["id"] for m in d.get("messages", [])]


# ---------- Reading one email ----------

def _b64(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _html_to_text(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", s)).strip()


def _body(payload: dict) -> str:
    plain, rich = [], []

    def walk(part):
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if part.get("filename"):
            return  # attachment
        if mime == "text/plain" and data:
            plain.append(_b64(data))
        elif mime == "text/html" and data:
            rich.append(_b64(data))
        for p in part.get("parts", []) or []:
            walk(p)

    walk(payload)
    text = "\n".join(plain).strip() or _html_to_text("\n".join(rich))
    return strip_quoted(text)[:MAX_BODY]


def strip_quoted(text: str) -> str:
    """Drop the quoted earlier conversation below "On <date>, <name> wrote:" so the AI reads only the new part."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^\s*On .{5,200} wrote:\s*$", line) or line.strip().startswith("-----Original Message"):
            kept = "\n".join(lines[:i]).strip()
            return kept or text
    kept = [ln for ln in lines if not ln.startswith(">")]
    return "\n".join(kept).strip() or text


def fetch(mailbox, message_id: str) -> dict:
    m = call(mailbox, "GET", f"/messages/{message_id}?format=full")
    headers = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
    from_name, from_email = parseaddr(headers.get("from", ""))
    reply_to = [a for _, a in getaddresses([headers["reply-to"]])] if headers.get("reply-to") else []
    return {
        "id": m["id"], "thread_id": m.get("threadId"), "labels": m.get("labelIds", []),
        "headers": headers, "from_name": (from_name or from_email.split("@")[0])[:200],
        "from_email": from_email.lower()[:320], "reply_to": (reply_to[0] if reply_to else "")[:320],
        "subject": (headers.get("subject") or "(no subject)")[:500],
        "rfc_message_id": headers.get("message-id", "")[:998],
        "references": headers.get("references", ""),
        "body": _body(m.get("payload", {})) or "(empty email)",
    }


SKIP_LABELS = {"SENT", "DRAFT", "SPAM", "TRASH", "CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL",
               "CATEGORY_UPDATES", "CATEGORY_FORUMS"}
NO_REPLY = re.compile(r"(^|[._+-])(no-?reply|do-?not-?reply|mailer-daemon|postmaster|bounces?|notifications?)([._+-]|@)",
                      re.I)


def skip_reason(email: dict, own_address: str):
    """Why the AI should NOT answer this email (None = answer it). Stops replies to robots and loops."""
    h = email["headers"]
    if email["from_email"] == own_address.lower():
        return "sent by this mailbox"
    if bad := SKIP_LABELS.intersection(email["labels"]):
        return f"Gmail label {sorted(bad)[0]}"
    if h.get("auto-submitted", "no").lower() != "no":
        return "auto-reply"
    if h.get("precedence", "").lower() in {"bulk", "list", "junk"}:
        return "bulk mail"
    if "list-id" in h or "list-unsubscribe" in h:
        return "mailing list / newsletter"
    if "x-autoreply" in h or "x-autorespond" in h:
        return "auto-reply"
    if NO_REPLY.search(email["from_email"]):
        return "no-reply sender"
    return None


# ---------- Replying ----------

def send_reply(mailbox, *, to: str, subject: str, body: str, thread_id=None, in_reply_to="", references="",
               automatic=False):
    msg = EmailMessage()
    msg["To"] = to
    msg["From"] = mailbox.email_address
    msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    msg["Message-ID"] = make_msgid(domain=mailbox.email_address.split("@")[-1])
    if automatic:  # standard header that stops other mail robots from answering back (no loops)
        msg["Auto-Submitted"] = "auto-replied"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = f"{references} {in_reply_to}".strip()
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    payload = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id
    return call(mailbox, "POST", "/messages/send", json=payload)
