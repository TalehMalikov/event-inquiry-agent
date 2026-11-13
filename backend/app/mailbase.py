"""Shared by the Gmail and Outlook connections."""


class MailError(Exception):
    """The mail provider refused or failed a request. The message is shown to the owner."""
