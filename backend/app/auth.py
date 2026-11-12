"""Login via Clerk. Users sign up/in on the frontend; every API call carries Clerk's signed session token.

We verify the token ourselves (Clerk's public keys, no network call per request) and read which
company (Clerk "organization") the user is working in. The company always comes from the token,
never from the request body or URL, so one company can never reach another company's data."""
import base64
import logging
from dataclasses import dataclass
from functools import lru_cache

import httpx
import jwt
from fastapi import HTTPException, Request

from .config import CLERK_AUTHORIZED_PARTIES, CLERK_PUBLISHABLE_KEY, CLERK_SECRET_KEY

log = logging.getLogger(__name__)


@dataclass
class Ctx:
    user_id: str
    org_id: str
    role: str  # "admin" or "member"

    @property
    def is_admin(self):
        return self.role == "admin"


def check_config():
    if not CLERK_PUBLISHABLE_KEY.startswith(("pk_test_", "pk_live_")):
        raise RuntimeError("Set CLERK_PUBLISHABLE_KEY (from the Clerk dashboard / Vercel)")


def _frontend_api():
    """The publishable key is base64 of Clerk's Frontend API host, e.g. 'xyz.clerk.accounts.dev$'."""
    enc = CLERK_PUBLISHABLE_KEY.split("_", 2)[2]
    return base64.b64decode(enc + "=" * (-len(enc) % 4)).decode().rstrip("$")


@lru_cache(maxsize=1)
def _jwks():
    return jwt.PyJWKClient(f"https://{_frontend_api()}/.well-known/jwks.json", cache_keys=True)


def _token(request: Request):
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get("__session")


def _verify(token: str) -> dict:
    try:
        key = _jwks().get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], leeway=10,
                            options={"require": ["exp", "iat", "sub"]})
    except jwt.PyJWTError as e:
        raise HTTPException(401, "Not logged in") from e
    azp = claims.get("azp")  # the site the token was issued for (absent on server-minted tokens)
    if CLERK_AUTHORIZED_PARTIES and azp and azp not in CLERK_AUTHORIZED_PARTIES:
        raise HTTPException(401, "Not logged in")
    if claims.get("sts") == "pending":  # signed in but hasn't finished a required step (choosing a company)
        raise HTTPException(403, "Choose or create a company first")
    return claims


def require_user(request: Request) -> Ctx:
    """FastAPI dependency: a logged-in user working inside a company."""
    token = _token(request)
    if not token:
        raise HTTPException(401, "Not logged in")
    claims = _verify(token)
    org = claims.get("o") or {}  # session token v2
    org_id = org.get("id") or claims.get("org_id")  # v1 fallback
    if not org_id:
        raise HTTPException(403, "Choose or create a company first")
    role = (org.get("rol") or claims.get("org_role") or "member").removeprefix("org:")
    return Ctx(user_id=claims["sub"], org_id=org_id, role=role)


def org_name(org_id: str) -> str:
    """Company name from Clerk, used once when we first see a company."""
    if not CLERK_SECRET_KEY:
        return "My company"
    try:
        r = httpx.get(f"https://api.clerk.com/v1/organizations/{org_id}",
                      headers={"Authorization": f"Bearer {CLERK_SECRET_KEY}"}, timeout=5)
        r.raise_for_status()
        return r.json().get("name") or "My company"
    except Exception as e:  # noqa: BLE001
        log.warning("Could not fetch organization name: %s", e)
        return "My company"


def rename_org(org_id: str, name: str):
    """Keep Clerk's company name (shown in the company switcher) in sync with ours."""
    if not CLERK_SECRET_KEY:
        return
    try:
        httpx.patch(f"https://api.clerk.com/v1/organizations/{org_id}", json={"name": name},
                    headers={"Authorization": f"Bearer {CLERK_SECRET_KEY}"}, timeout=5).raise_for_status()
    except Exception as e:  # noqa: BLE001
        log.warning("Could not rename organization in Clerk: %s", e)
