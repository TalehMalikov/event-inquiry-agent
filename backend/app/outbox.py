"""Everything the agent does in the owner's mailbox: drafts, colored labels, sending, and the phone ping.

The colors live only in the owner's Gmail (labels) and in our app. Customers only ever receive the reply text.
Drafts and labels are a convenience: if Gmail refuses one of them, the reply flow still works.
"""
import logging

from . import gmail, push
from .db import Mailbox, Message, SessionLocal

log = logging.getLogger("outbox")

PING_DOT = {"yellow": "🟡", "red": "🔴"}


def _load(s, message_id):
    m = s.get(Message, message_id)
    mb = s.get(Mailbox, m.mailbox_id) if m and m.mailbox_id else None
    if mb is not None and mb.company_id != m.company_id:
        mb = None
    return m, mb


def _labels(s, mb):
    if not gmail.can_draft(mb):
        return None
    if not mb.label_ids:
        mb.label_ids = gmail.ensure_labels(mb)
        s.commit()
    return mb.label_ids


def _set_label(s, m, mb, color):
    try:
        if (ids := _labels(s, mb)) and m.external_id:
            gmail.set_color_label(mb, ids, m.external_id, color)
    except gmail.GmailError as e:
        log.warning("Label failed for message %s: %s", m.id, e)


def _drop_draft(s, m, mb):
    if m.draft_external_id and mb is not None:
        gmail.delete_draft(mb, m.draft_external_id)
        m.draft_external_id = None
        s.commit()


def stage(message_id: int, color: str, reply: str, make_draft: bool):
    """Yellow/red: put the draft in the Gmail thread, color the thread, ping the owner's phone."""
    with SessionLocal() as s:
        m, mb = _load(s, message_id)
        if mb is not None:
            _set_label(s, m, mb, color)
            if make_draft and gmail.can_draft(mb) and not m.draft_external_id:
                try:
                    m.draft_external_id = gmail.create_draft(
                        mb, to=m.reply_to or m.from_email, subject=m.subject, body=reply,
                        thread_id=m.external_thread_id, in_reply_to=m.rfc_message_id or "",
                        references=m.email_references or "")
                    s.commit()
                except gmail.GmailError as e:
                    log.warning("Draft failed for message %s: %s", message_id, e)
        title = f"{PING_DOT.get(color, '🟡')} {m.from_name}: {m.subject}"[:120]
        company_id = m.company_id
    # Yellow: Send / Decline right on the notification. Red: no Send button; the owner opens it.
    actions = []
    if color == "yellow":
        actions = [{"action": "approve", "title": "Send", "token": push.action_token(message_id, "approve")},
                   {"action": "reject", "title": "Decline", "token": push.action_token(message_id, "reject")}]
    push.notify_company(company_id, title=title, url=f"/m/{message_id}", tag=f"msg-{message_id}",
                        actions=actions)


def send(message_id: int, body: str, automatic: bool):
    """Send the reply from the company's own mailbox, in the same thread. Then tidy up Gmail."""
    with SessionLocal() as s:
        m, mb = _load(s, message_id)
        if mb is None:
            raise RuntimeError("No connected mailbox to send from. Connect Gmail in Settings.")
        sent = gmail.send_reply(mb, to=m.reply_to or m.from_email, subject=m.subject, body=body,
                                thread_id=m.external_thread_id, in_reply_to=m.rfc_message_id or "",
                                references=m.email_references or "", automatic=automatic)
        m.sent_external_id = (sent or {}).get("id")
        s.commit()
        _drop_draft(s, m, mb)  # approved in our app: the Gmail draft would be a confusing leftover
        _set_label(s, m, mb, "green")
    log.info("Sent reply for message %s", message_id)


def mark_sent_in_gmail(message_id: int):
    """The owner replied from Gmail. Our draft is gone if they sent it; if they wrote their own, remove ours."""
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
