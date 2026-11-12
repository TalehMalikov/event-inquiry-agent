"""Where replies actually go out: the company's connected mailbox, as a reply in the same thread."""
import logging

from . import gmail
from .db import Mailbox, Message, SessionLocal

log = logging.getLogger("outbox")


def send(message_id: int, body: str, automatic: bool):
    with SessionLocal() as s:
        m = s.get(Message, message_id)
        mailbox = s.get(Mailbox, m.mailbox_id) if m.mailbox_id else None
        if mailbox is None or mailbox.company_id != m.company_id:
            raise RuntimeError("No connected mailbox to send from. Connect Gmail in Settings.")
        gmail.send_reply(mailbox, to=m.reply_to or m.from_email, subject=m.subject, body=body,
                         thread_id=m.external_thread_id, in_reply_to=m.rfc_message_id or "",
                         references=m.email_references or "", automatic=automatic)
    log.info("Sent reply for message %s from %s", message_id, mailbox.email_address)
