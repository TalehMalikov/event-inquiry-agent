"""Where replies actually go out.

MVP: simulated (logged only). Next step: swap this for the Microsoft Graph API (Outlook).
"""
import logging

log = logging.getLogger("outbox")


def send(to: str, subject: str, body: str):
    log.info("SIMULATED SEND to=%s subject=%r\n%s", to, subject, body)
