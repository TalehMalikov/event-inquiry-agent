"""Owner login: one password per deployment, kept in a signed HttpOnly cookie."""
import hmac
import time

from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import COOKIE_SECURE, OWNER_PASSWORD, SESSION_DAYS, SESSION_SECRET

COOKIE = "vi_session"
MAX_AGE = SESSION_DAYS * 24 * 3600


def check_config():
    """Refuse to start without real credentials, so the app is never deployed unprotected."""
    if not OWNER_PASSWORD or OWNER_PASSWORD == "change-me":
        raise RuntimeError("Set OWNER_PASSWORD in backend/.env")
    if len(SESSION_SECRET) < 32 or SESSION_SECRET.startswith("change-me"):
        raise RuntimeError("Set SESSION_SECRET in backend/.env to a random string of 32+ characters")


def _serializer():
    return URLSafeTimedSerializer(SESSION_SECRET, salt="owner-session")


def login(password: str, response: Response):
    if not hmac.compare_digest(password.encode(), OWNER_PASSWORD.encode()):
        time.sleep(0.5)  # slow down password guessing
        raise HTTPException(401, "Wrong password")
    token = _serializer().dumps({"role": "owner"})
    response.set_cookie(COOKIE, token, max_age=MAX_AGE, httponly=True, samesite="lax",
                        secure=COOKIE_SECURE, path="/")


def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")


def is_logged_in(request: Request) -> bool:
    token = request.cookies.get(COOKIE)
    if not token:
        return False
    try:
        return _serializer().loads(token, max_age=MAX_AGE).get("role") == "owner"
    except (BadSignature, SignatureExpired):
        return False


def require_owner(request: Request):
    """FastAPI dependency for every owner-only endpoint."""
    if not is_logged_in(request):
        raise HTTPException(401, "Not logged in")
