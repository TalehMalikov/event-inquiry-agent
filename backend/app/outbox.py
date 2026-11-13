"""Everything the agent does in the owner's mailbox: drafts, colored labels, sending, and the phone ping.

Works for Gmail (labels) and Outlook (categories) through providers.py.
The colors live only in the owner's mailbox and in our app. Customers only ever receive the reply text.
Drafts and labels are a convenience: if the mailbox refuses one of them, the reply flow still works.
"""
import logging

from . import providers, push
from .db import Mailbox, Message, SessionLocal
from .mailbase import MailError

log = logging.getLogger("outbox")

PING_DOT = {"yellow": "🟡", "red": "🔴"}

def _load(s, message_id):
    m = s.get(Message, message_id)
    mb = s.get(Mailbox, m.mailbox_id) if m and m.mailbox_id else None
    if mb is not None and mb.company_id != m.company_id:
        mb = None
    return m, mb

def _labels(s, mb):
    if not providers.of(mb).can_draft(mb):
        return None
    if not mb.label_ids:
        mb.label_ids = providers.of(mb).ensure_labels(mb)
        s.commit()
    return mb.label_ids

def _set_label(s, m, mb, color):
    try:
        if (ids := _labels(s, mb)) and m.external_id:
            providers.of(mb).set_color_label(mb, ids, m.external_id, color)
    except MailError as e:
        log.warning("Label failed for message %s: %s", m.id, e)

def _drop_draft(s, m, mb):
    if m.draft_external_id and mb is not None:
        providers.of(mb).delete_draft(mb, m.draft_external_id)
        m.draft_external_id = None
        s.commit()

def stage(message_id: int, color: str, reply: str, make_draft: bool):
    """Yellow/red: put the draft in the Gmail thread, color the thread, ping the owner's phone."""
    with SessionLocal() as s:
        m, mb = _load(s, message_id)
        if mb is not None:
            _set_label(s, m, mb, color)
            if make_draft and providers.of(mb).can_draft(mb) and not m.draft_external_id:
                try:
                    m.draft_external_id = providers.of(mb).create_draft(
                        mb, to=m.reply_to or m.from_email, subject=m.subject, body=reply,
                        thread_id=m.external_thread_id, in_reply_to=m.rfc_message_id or "",
                        references=m.email_references or "", reply_to_id=m.external_id)
                    s.commit()
                except MailError as e:
                    log.warning("Draft failed for message %s: %s", message_id, e)
        who = (m.from_name or m.from_email or "a customer").split()[0][:40]  # first name only: short and calm
        title = f"🟡 Approve reply to {who}" if color == "yellow" else f"🔴 {who} needs you"
        company_id = m.company_id
    # Yellow: Send / Decline right on the notification. Red: no Send button; the owner opens it.
    actions = []
    if color == "yellow":
        actions = [{"action": "approve", "title": "Send", "token": push.action_token(message_id, "approve")},
                   {"action": "reject", "title": "Decline", "token": push.action_token(message_id, "reject")}]
    push.notify_company(company_id, title=title, url=f"/m/{message_id}", tag=f"msg-{message_id}",
                        actions=actions)

def send(message_id: int, body: str, automatic: bool):
    """Send the reply from the company's own mailbox, in the same thread. Then tidy up the drafts and colors."""
    with SessionLocal() as s:
        m, mb = _load(s, message_id)
        if mb is None:
            raise RuntimeError("No connected mailbox to send from. Connect your inbox in Settings.")
        sent = providers.of(mb).send_reply(
            mb, to=m.reply_to or m.from_email, subject=m.subject, body=body, thread_id=m.external_thread_id,
            in_reply_to=m.rfc_message_id or "", references=m.email_references or "", automatic=automatic,
            reply_to_id=m.external_id, draft_id=m.draft_external_id)
        m.sent_external_id = (sent or {}).get("id")
        if (sent or {}).get("used_draft"):
            m.draft_external_id = None  # Outlook sent our draft itself: it is now the sent email, not a leftover
        s.commit()
        _drop_draft(s, m, mb)  # approved in our app: the Gmail draft would be a confusing leftover
        _set_label(s, m, mb, "green")
    log.info("Sent reply for message %s", message_id)

def mark_sent_in_gmail(message_id: int):
    """The owner replied from their mailbox. Our draft is gone if they sent it; if they wrote their own, remove ours."""
    with SessionLocal() as s:
        m, mb = _load(s, message_id)
        if mb is None:
            return
        _drop_draft(s, m, mb)
        _set_label(s, m, mb, "green")

def discard(message_id: int):
    """Rejected: remove our draft and color, leave the email itself alone."""
    with SessionLocal() as s:
        m, mb = _load(s, message_id)
        if mb is None:
            return
        _drop_draft(s, m, mb)
        _set_label(s, m, mb, None)
