"""Which mail service a mailbox uses. gmail.py and outlook.py offer the same functions, so the rest of the app
(ingest, drafts, labels, sending) is written once and works for both."""
from . import gmail, outlook

PROVIDERS = {"gmail": gmail, "outlook": outlook}


def get(name: str):
    return PROVIDERS[name]


def of(mailbox):
    return PROVIDERS.get(mailbox.provider or "gmail", gmail)
