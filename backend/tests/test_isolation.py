"""Company isolation + Gmail pipeline test.

Company A must never see or touch company B's data or mailbox. Runs against a scratch Postgres
database (default: the Docker one, database "isotest") with fake Clerk tokens signed by a throwaway
key and a fake Gmail (no Google or OpenAI calls). The LLM agent is replaced by a stub.

    docker compose up -d db
    .venv/Scripts/python tests/test_isolation.py
"""
import base64
import json
import os
import sys
import time
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import psycopg  # noqa: E402

ADMIN_URL = "postgresql://inbox:inbox@localhost:5433/inbox"
with psycopg.connect(ADMIN_URL, autocommit=True) as c:
    c.execute("DROP DATABASE IF EXISTS isotest WITH (FORCE)")
    c.execute("CREATE DATABASE isotest")
from cryptography.fernet import Fernet  # noqa: E402

os.environ.update({
    "DATABASE_URL": "postgresql://inbox:inbox@localhost:5433/isotest",
    "CLERK_PUBLISHABLE_KEY": "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk", "CLERK_SECRET_KEY": "",
    "CLERK_AUTHORIZED_PARTIES": "http://localhost:3000", "DAILY_DRAFT_LIMIT": "3",
    "GOOGLE_CLIENT_ID": "test-client", "GOOGLE_CLIENT_SECRET": "test-secret", "GOOGLE_PROJECT_ID": "test-proj",
    "GMAIL_PUSH_TOKEN": "push-secret", "GMAIL_PUBSUB_TOPIC": "gmail-push", "CRON_SECRET": "cron-secret",
    "MAILBOX_ENCRYPTION_KEY": Fernet.generate_key().decode(),
})

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app import agent, auth, gmail, mail_api, main, outbox, rag  # noqa: E402
from app.db import Mailbox  # noqa: E402

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
auth._jwks = lambda: type("J", (), {"get_signing_key_from_jwt": lambda self, t: type("K", (), {"key": KEY.public_key()})()})()
rag.try_embed = lambda texts: None  # no OpenAI calls; search falls back to "all of this company's policies"


def fake_process(message_id):
    """Stand-in for the LLM agent: records which company's policies the agent was given."""
    with main.SessionLocal() as s:
        m = s.get(main.Message, message_id)
        m.facts = {"policies": rag.search(s, m.company_id, m.body)}
        m.status, m.color, m.draft = "waiting", "yellow", "stub draft"
        s.commit()


main.process_message = fake_process
mail_api.process_message = fake_process


# ---------- Fake Gmail: one inbox per address, with a history counter like the real API ----------

class FakeGmail:
    def __init__(self):
        self.inbox = {}  # address -> list of (history_id, message dict)
        self.history = 100
        self.sent = []
        self.watches = 0

    def deliver(self, to, sender, subject="Hello", body="Hi there", headers=None, labels=("INBOX",), reply_to=""):
        self.history += 1
        gid = f"g{self.history}"
        h = {"from": sender, "subject": subject, "message-id": f"<{gid}@mail.example>", **(headers or {})}
        if reply_to:
            h["reply-to"] = reply_to
        name, addr = (sender.split("<")[0].strip(), sender.split("<")[1].rstrip(">")) if "<" in sender else ("", sender)
        self.inbox.setdefault(to, []).append((self.history, {
            "id": gid, "thread_id": f"t{gid}", "labels": list(labels), "headers": {k.lower(): v for k, v in h.items()},
            "from_name": name or addr.split("@")[0], "from_email": addr.lower(), "reply_to": reply_to,
            "subject": subject, "rfc_message_id": h["message-id"], "references": "", "body": body}))
        return gid


G = FakeGmail()
gmail.exchange_code = lambda code: {"access_token": "at:" + code, "refresh_token": "rt:" + code,
                                    "scope": " ".join(gmail.SCOPES)}
gmail.profile_with_token = lambda tok: {"emailAddress": tok.split(":", 1)[1], "historyId": str(G.history)}
gmail.access_token = lambda mb: "at:" + mb.email_address
gmail.watch = lambda mb: (setattr(G, "watches", G.watches + 1),
                          {"historyId": str(G.history), "expiration": str(int((time.time() + 7 * 86400) * 1000))})[1]
gmail.stop = lambda mb: None
gmail.revoke = lambda t: None
gmail.new_message_ids = lambda mb, start: ([m["id"] for hid, m in G.inbox.get(mb.email_address, []) if hid > int(start)],
                                           str(G.history))
gmail.fetch = lambda mb, gid: next(m for _, m in G.inbox[mb.email_address] if m["id"] == gid)
gmail.send_reply = lambda mb, **kw: G.sent.append({"from": mb.email_address, **kw})


def token(org, user="user_1", role="org:admin", azp="http://localhost:3000", **extra):
    now = int(time.time())
    claims = {"sub": user, "iat": now, "exp": now + 60, "azp": azp, "v": 2,
              "o": {"id": org, "rol": role.removeprefix("org:")} if org else None, **extra}
    claims = {k: v for k, v in claims.items() if v is not None}
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="RS256")}


def push(client, address, tok="push-secret"):
    data = base64.b64encode(json.dumps({"emailAddress": address, "historyId": G.history}).encode()).decode()
    return client.post(f"/api/gmail/push?token={tok}", json={"message": {"data": data}})


def connect(client, headers, address):
    url = client.post("/api/gmail/connect", headers=headers).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    return client.post("/api/gmail/callback", headers=headers, json={"code": address, "state": state})


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
    check("simulator is gone", client.post("/api/messages/simulate", headers=A, json={"body": "x"}).status_code in (404, 405))

    # --- each company gets its own data ---
    client.put("/api/settings", headers=A, json={"company_name": "Alpha Hall", "green_categories": ["info"]})
    client.put("/api/settings", headers=B, json={"company_name": "Beta Loft", "green_categories": []})
    check("A sees its own name", client.get("/api/settings", headers=A).json()["company_name"] == "Alpha Hall")
    check("B sees its own name", client.get("/api/settings", headers=B).json()["company_name"] == "Beta Loft")
    client.put("/api/rooms", headers=B, json=[{"name": "Beta Room", "capacity": 10, "weekday_min": 1, "weekend_min": 2}])
    check("A's rooms untouched by B", "Beta Room" not in [r["name"] for r in client.get("/api/rooms", headers=A).json()])
    client.post("/api/policies", headers=B, json={"text": "SECRET-B: Beta's private policy"})
    check("A can't see B's policy", not any("SECRET-B" in p["text"] for p in client.get("/api/policies", headers=A).json()))
    b_pid = [p["id"] for p in client.get("/api/policies", headers=B).json() if "SECRET-B" in p["text"]][0]
    client.delete(f"/api/policies/{b_pid}", headers=A)
    check("A can't delete B's policy", any(p["id"] == b_pid for p in client.get("/api/policies", headers=B).json()))

    # --- connecting Gmail ---
    member = token("org_A", "user_m", role="org:member")
    check("not connected at first", client.get("/api/gmail", headers=A).json()["connected"] is False)
    check("member can't connect Gmail", client.post("/api/gmail/connect", headers=member).status_code == 403)
    url_a = client.post("/api/gmail/connect", headers=A).json()["url"]
    state_a = parse_qs(urlparse(url_a).query)["state"][0]
    check("Google URL asks only for read + send", set(parse_qs(urlparse(url_a).query)["scope"][0].split()) == set(gmail.SCOPES))
    check("A's sign-in can't be finished by B (CSRF)",
          client.post("/api/gmail/callback", headers=B, json={"code": "evil@gmail.com", "state": state_a}).status_code == 400)
    check("forged state rejected",
          client.post("/api/gmail/callback", headers=A, json={"code": "alpha@gmail.com", "state": "x.y.z"}).status_code == 400)
    r = connect(client, A, "alpha@gmail.com")
    check("A connects alpha@gmail.com", r.status_code == 200 and r.json()["email"] == "alpha@gmail.com")
    check("B connects beta@gmail.com", connect(client, B, "beta@gmail.com").status_code == 200)
    check("B can't take A's address", connect(client, B, "alpha@gmail.com").status_code == 409)
    check("B still has its own address", client.get("/api/gmail", headers=B).json()["email"] == "beta@gmail.com")
    with main.SessionLocal() as s:
        enc = s.scalar(select(Mailbox.refresh_token_enc).where(Mailbox.email_address == "alpha@gmail.com"))
    check("Gmail token stored encrypted", "rt:alpha" not in enc and gmail.decrypt(enc) == "rt:alpha@gmail.com")

    # --- receiving email ---
    G.deliver("alpha@gmail.com", "Jane Doe <jane@customer.com>", "Party for 40?", "Can we book for 40 people?",
              reply_to="jane.replies@customer.com")
    check("push with wrong token -> 403", push(client, "alpha@gmail.com", tok="nope").status_code == 403)
    check("push accepted", push(client, "alpha@gmail.com").status_code == 204)
    msgs_a = client.get("/api/messages", headers=A).json()
    check("A received the email", len(msgs_a) == 1 and msgs_a[0]["from_email"] == "jane@customer.com")
    check("B received nothing", client.get("/api/messages", headers=B).json() == [])
    push(client, "alpha@gmail.com")
    check("repeated notification -> no duplicate", len(client.get("/api/messages", headers=A).json()) == 1)
    check("push for unknown address is ignored", push(client, "stranger@gmail.com").status_code == 204)

    G.deliver("alpha@gmail.com", "News <news@shop.com>", "Sale!", "50% off", headers={"List-Unsubscribe": "<mailto:u@shop.com>"})
    G.deliver("alpha@gmail.com", "noreply@bank.com", "Statement", "Your statement")
    G.deliver("alpha@gmail.com", "Bot <bot@x.com>", "Out of office", "I'm away", headers={"Auto-Submitted": "auto-replied"})
    G.deliver("alpha@gmail.com", "alpha@gmail.com", "Note to self", "hi")
    G.deliver("alpha@gmail.com", "Promo <deals@x.com>", "Deals", "deal", labels=("INBOX", "CATEGORY_PROMOTIONS"))
    push(client, "alpha@gmail.com")
    check("newsletters / no-reply / auto-replies / own mail / promotions skipped",
          len(client.get("/api/messages", headers=A).json()) == 1)

    G.deliver("beta@gmail.com", "Bob <bob@client.com>", "Hi Beta", "Question for Beta")
    check("manual 'check for new mail' works", client.post("/api/gmail/sync", headers=B).json()["new"] == 1)
    mb_b = client.get("/api/messages", headers=B).json()
    check("B's agent got B's policy", any("SECRET-B" in t for t in mb_b[0]["facts"]["policies"]))
    check("A's agent never got B's policy", not any("SECRET-B" in t for t in msgs_a[0]["facts"]["policies"]))
    check("A can't approve B's message", client.post(f"/api/messages/{mb_b[0]['id']}/approve", headers=A, json={}).status_code == 404)
    check("A can't reject B's message", client.post(f"/api/messages/{mb_b[0]['id']}/reject", headers=A).status_code == 404)
    check("A can't retry B's message", client.post(f"/api/messages/{mb_b[0]['id']}/retry", headers=A).status_code == 404)

    # --- replying ---
    outbox.send(msgs_a[0]["id"], "Yes, we can host 40!", automatic=False)
    sent = G.sent[-1]
    check("reply sent from A's own Gmail", sent["from"] == "alpha@gmail.com")
    check("reply goes to the Reply-To address", sent["to"] == "jane.replies@customer.com")
    check("reply stays in the same Gmail thread", sent["thread_id"] == "tg101")
    check("reply references the original email", sent["in_reply_to"].startswith("<g") and sent["subject"] == "Party for 40?")
    check("approved reply isn't marked automatic", sent["automatic"] is False)
    gmail.send_reply = lambda mb, **kw: (_ for _ in ()).throw(gmail.GmailError("quota"))
    upd = agent.send({"message_id": msgs_a[0]["id"], "color": "green", "draft": {"reply": "hi"}})
    check("send failure is shown, not lost", upd["status"] == "error" and "quota" in upd["send_error"])
    gmail.send_reply = lambda mb, **kw: G.sent.append({"from": mb.email_address, **kw})

    # --- roles ---
    check("member can read inbox", client.get("/api/messages", headers=member).status_code == 200)
    check("member can't change settings", client.put("/api/settings", headers=member, json={"company_name": "X", "green_categories": []}).status_code == 403)
    check("member can't disconnect Gmail", client.delete("/api/gmail", headers=member).status_code == 403)

    # --- daily limit is per company (limit 3) ---
    for i in range(3):
        G.deliver("alpha@gmail.com", f"C{i} <c{i}@x.org>", f"Q{i}", "question")
    push(client, "alpha@gmail.com")
    statuses = [m["status"] for m in client.get("/api/messages", headers=A).json()]
    check("A's 4th email of the day waits with a limit error", statuses.count("error") == 1 and len(statuses) == 4)
    G.deliver("beta@gmail.com", "Bob <bob@client.com>", "Again", "Another one")
    push(client, "beta@gmail.com")
    check("B unaffected by A's limit", all(m["status"] == "waiting" for m in client.get("/api/messages", headers=B).json()))

    # --- daily job ---
    check("cron without secret -> 401", client.get("/api/cron/gmail").status_code == 401)
    before = G.watches
    with main.SessionLocal() as s:  # make A's watch nearly expired
        mb = s.scalar(select(Mailbox).where(Mailbox.email_address == "alpha@gmail.com"))
        mb.watch_expires_at = main.utcnow()
        s.commit()
    r = client.get("/api/cron/gmail", headers={"Authorization": "Bearer cron-secret"})
    check("cron renews expiring Gmail watch", r.status_code == 200 and r.json()["renewed"] == 1 and G.watches == before + 1)

    # --- without Pub/Sub (no Google billing): connect without a watch, scheduled check picks up mail ---
    gmail.push_enabled = lambda: False
    C = token("org_C", "user_c")
    watches_before = G.watches
    check("C connects without push", connect(client, C, "gamma@gmail.com").status_code == 200
          and G.watches == watches_before)
    G.deliver("gamma@gmail.com", "Carol <carol@client.com>", "Hours?", "When are you open?")
    r = client.get("/api/cron/gmail", headers={"Authorization": "Bearer cron-secret"})
    check("scheduled check fetches C's new mail", r.status_code == 200
          and [m["from_email"] for m in client.get("/api/messages", headers=C).json()] == ["carol@client.com"])
    check("scheduled check doesn't renew watches without push", r.json()["renewed"] == 0)
    check("scheduled check gave nothing new to A or B", len(client.get("/api/messages", headers=A).json()) == 4)
    gmail.push_enabled = lambda: True

    # --- disconnect ---
    check("A disconnects", client.delete("/api/gmail", headers=A).json()["connected"] is False)
    check("A's emails kept after disconnect", len(client.get("/api/messages", headers=A).json()) == 4)
    check("B still connected", client.get("/api/gmail", headers=B).json()["connected"] is True)

# --- email parsing (pure functions) ---
check("quoted history removed", gmail.strip_quoted("Yes please\n\nOn Mon, Jan 1, 2026 at 9:00 AM Bob <b@x.com> wrote:\n> old") == "Yes please")
check("html email turned into text", "Hello world" in gmail._html_to_text("<p>Hello <b>world</b></p><style>x{}</style>"))

main._pool.close()
from app.db import engine  # noqa: E402

engine.dispose()
with psycopg.connect(ADMIN_URL, autocommit=True) as c:
    c.execute("DROP DATABASE IF EXISTS isotest WITH (FORCE)")

print(f"\n{'ALL PASSED' if not fails else f'{fails} FAILED'}")
sys.exit(1 if fails else 0)
