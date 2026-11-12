"""Company isolation test: company A must never see or touch company B's data.

Runs against a scratch Postgres database (default: the Docker one, database "isotest") with
fake Clerk tokens signed by a throwaway key. The OpenAI agent is replaced by a stub.

    docker compose up -d db
    .venv/Scripts/python tests/test_isolation.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import psycopg  # noqa: E402

ADMIN_URL = "postgresql://inbox:inbox@localhost:5433/inbox"
with psycopg.connect(ADMIN_URL, autocommit=True) as c:
    c.execute("DROP DATABASE IF EXISTS isotest")
    c.execute("CREATE DATABASE isotest")
os.environ["DATABASE_URL"] = "postgresql://inbox:inbox@localhost:5433/isotest"
os.environ["CLERK_PUBLISHABLE_KEY"] = "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk"
os.environ["CLERK_SECRET_KEY"] = ""
os.environ["CLERK_AUTHORIZED_PARTIES"] = "http://localhost:3000"
os.environ["DAILY_DRAFT_LIMIT"] = "3"

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import auth, main, rag  # noqa: E402

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJWKS:
    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": KEY.public_key()})()


auth._jwks = lambda: FakeJWKS()
rag.try_embed = lambda texts: None  # no OpenAI calls; search falls back to "all of this company's policies"


def fake_process(message_id):
    """Stand-in for the LLM agent: records which company's policies the agent was given."""
    with main.SessionLocal() as s:
        m = s.get(main.Message, message_id)
        m.facts = {"policies": rag.search(s, m.company_id, m.body)}
        m.status, m.color, m.draft = "waiting", "yellow", "stub draft"
        s.commit()


main.process_message = fake_process


def token(org, user="user_1", role="org:admin", azp="http://localhost:3000", **extra):
    now = int(time.time())
    claims = {"sub": user, "iat": now, "exp": now + 60, "azp": azp, "v": 2,
              "o": {"id": org, "rol": role.removeprefix("org:")} if org else None, **extra}
    claims = {k: v for k, v in claims.items() if v is not None}
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="RS256")}


A, B = token("org_A", "user_a"), token("org_B", "user_b")
fails = 0


def check(name, cond):
    global fails
    print(("PASS " if cond else "FAIL ") + name)
    fails += not cond


with TestClient(main.app) as client:
    # --- login is required, and tokens must be real and for our site ---
    check("no token -> 401", client.get("/api/messages").status_code == 401)
    check("garbage token -> 401", client.get("/api/messages", headers={"Authorization": "Bearer x.y.z"}).status_code == 401)
    check("token for another site -> 401", client.get("/api/messages", headers=token("org_A", azp="https://evil.example")).status_code == 401)
    check("signed in but no company -> 403", client.get("/api/messages", headers=token(None)).status_code == 403)
    check("pending session -> 403", client.get("/api/messages", headers=token("org_A", sts="pending")).status_code == 403)

    # --- each company gets its own data ---
    client.put("/api/settings", headers=A, json={"company_name": "Alpha Hall", "green_categories": ["info"]})
    client.put("/api/settings", headers=B, json={"company_name": "Beta Loft", "green_categories": []})
    check("A sees its own name", client.get("/api/settings", headers=A).json()["company_name"] == "Alpha Hall")
    check("B sees its own name", client.get("/api/settings", headers=B).json()["company_name"] == "Beta Loft")

    client.put("/api/rooms", headers=B, json=[{"name": "Beta Room", "capacity": 10, "weekday_min": 1, "weekend_min": 2}])
    check("B's rooms replaced", [r["name"] for r in client.get("/api/rooms", headers=B).json()] == ["Beta Room"])
    check("A's rooms untouched", "Beta Room" not in [r["name"] for r in client.get("/api/rooms", headers=A).json()]
          and len(client.get("/api/rooms", headers=A).json()) == 2)

    client.post("/api/policies", headers=B, json={"text": "SECRET-B: Beta's private policy"})
    a_policies = [p["text"] for p in client.get("/api/policies", headers=A).json()]
    check("A can't see B's policy", not any("SECRET-B" in t for t in a_policies))
    b_policy_id = [p["id"] for p in client.get("/api/policies", headers=B).json() if "SECRET-B" in p["text"]][0]
    client.delete(f"/api/policies/{b_policy_id}", headers=A)
    check("A can't delete B's policy", any(p["id"] == b_policy_id for p in client.get("/api/policies", headers=B).json()))

    # --- messages and the agent's knowledge (RAG) ---
    ma = client.post("/api/messages/simulate", headers=A, json={"body": "Hi from a customer of A"}).json()
    mb = client.post("/api/messages/simulate", headers=B, json={"body": "Hi from a customer of B"}).json()
    check("A lists only A's messages", [m["id"] for m in client.get("/api/messages", headers=A).json()] == [ma["id"]])
    check("B lists only B's messages", [m["id"] for m in client.get("/api/messages", headers=B).json()] == [mb["id"]])
    check("A's agent never got B's policy", not any("SECRET-B" in t for t in ma["facts"]["policies"]))
    check("B's agent got B's policy", any("SECRET-B" in t for t in mb["facts"]["policies"]))
    check("A can't approve B's message", client.post(f"/api/messages/{mb['id']}/approve", headers=A, json={}).status_code == 404)
    check("A can't reject B's message", client.post(f"/api/messages/{mb['id']}/reject", headers=A).status_code == 404)
    check("A can't retry B's message", client.post(f"/api/messages/{mb['id']}/retry", headers=A).status_code == 404)

    # --- roles: members can work the inbox but not change company data ---
    member = token("org_A", "user_m", role="org:member")
    check("member can read inbox", client.get("/api/messages", headers=member).status_code == 200)
    check("member can't change settings", client.put("/api/settings", headers=member, json={"company_name": "X", "green_categories": []}).status_code == 403)
    check("member can't change rooms", client.put("/api/rooms", headers=member, json=[]).status_code == 403)
    check("member can't add policies", client.post("/api/policies", headers=member, json={"text": "nope nope"}).status_code == 403)

    # --- daily limit is per company ---
    for _ in range(2):
        client.post("/api/messages/simulate", headers=A, json={"body": "more"})
    check("A hits its limit (3/day)", client.post("/api/messages/simulate", headers=A, json={"body": "one too many"}).status_code == 429)
    check("B unaffected by A's limit", client.post("/api/messages/simulate", headers=B, json={"body": "still fine"}).status_code == 200)

main._pool.close()
from app.db import engine  # noqa: E402

engine.dispose()
with psycopg.connect(ADMIN_URL, autocommit=True) as c:
    c.execute("DROP DATABASE IF EXISTS isotest WITH (FORCE)")

print(f"\n{'ALL PASSED' if not fails else f'{fails} FAILED'}")
sys.exit(1 if fails else 0)
