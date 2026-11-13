"""Drafts-in-Gmail + colored labels + phone pings, through the REAL agent graph (only the two LLM calls
are replaced by canned answers). Fake Gmail and fake push service; scratch database "drafttest".

    docker compose up -d db
    .venv/Scripts/python tests/test_drafts.py
"""
import base64
import email as email_lib
import json
import os
import sys
import time
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import psycopg  # noqa: E402

ADMIN_URL = "postgresql://inbox:inbox@localhost:5433/inbox"
with psycopg.connect(ADMIN_URL, autocommit=True) as c:
    c.execute("DROP DATABASE IF EXISTS drafttest WITH (FORCE)")
    c.execute("CREATE DATABASE drafttest")
from cryptography.fernet import Fernet  # noqa: E402

os.environ.update({
    "DATABASE_URL": "postgresql://inbox:inbox@localhost:5433/drafttest",
    "CLERK_PUBLISHABLE_KEY": "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk", "CLERK_SECRET_KEY": "",
    "CLERK_AUTHORIZED_PARTIES": "http://localhost:3000", "DAILY_DRAFT_LIMIT": "50",
    "GOOGLE_CLIENT_ID": "c", "GOOGLE_CLIENT_SECRET": "s", "GOOGLE_PROJECT_ID": "p", "GMAIL_PUBSUB_TOPIC": "",
    "GMAIL_PUSH_TOKEN": "push-secret", "CRON_SECRET": "cron-secret",
    "MAILBOX_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    "VAPID_PUBLIC_KEY": "test-public", "VAPID_PRIVATE_KEY": "dGVzdA==",
})

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import agent, auth, gmail, push, rag  # noqa: E402

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
auth._jwks = lambda: type("J", (), {"get_signing_key_from_jwt": lambda self, t: type("K", (), {"key": KEY.public_key()})()})()
rag.try_embed = lambda texts: None


# ---------- Canned LLM answers, chosen by keywords in the email ----------

def fake_understand(state):
    body = state["email"].lower()
    if "refund" in body:
        cat, guests = "refund", None
    elif "120" in body:
        cat, guests = "inquiry", 120
    elif "book" in body:
        cat, guests = "inquiry", 40
    else:
        cat, guests = "info", None
    return {"request": {"category": cat, "guests": guests, "weekend": True, "budget": None, "summary": body[:40]}}


def fake_draft(state):
    req = state["request"]
    if req["category"] == "info":
        d = dict(reply="We're open Tue-Sun, 11am to 11pm.", quoted_prices=[], offered_price=None,
                 offered_guests=None, commits_to_date=False, needs_team_check=False)
    elif req["category"] == "refund":
        d = dict(reply="We're so sorry. The team will follow up personally.", quoted_prices=[], offered_price=None,
                 offered_guests=None, commits_to_date=False, needs_team_check=False)
    elif req["guests"] == 120:  # a WRONG draft: promises more guests than the biggest room fits
        d = dict(reply="Sure, we can host all 120 of you!", quoted_prices=[], offered_price=None,
                 offered_guests=120, commits_to_date=False, needs_team_check=False)
    else:
        d = dict(reply="The Main Hall fits 40, from $800 on Saturdays.", quoted_prices=[800], offered_price=800,
                 offered_guests=40, commits_to_date=False, needs_team_check=False)
    return {"draft": d}


agent.understand, agent.draft = fake_understand, fake_draft


# ---------- Fake Gmail with drafts, labels and the owner's own sends ----------

class FakeGmail:
    def __init__(self):
        self.inbox = {}  # address -> [(history id, message)]
        self.history = 100
        self.sent, self.drafts, self.labels, self.created_labels = [], {}, {}, []
        self.next_draft = 1

    def add(self, to, m):
        self.history += 1
        self.inbox.setdefault(to, []).append((self.history, m))

    def deliver(self, to, sender, subject, body):
        gid = f"g{self.history + 1}"
        name, addr = sender.split("<")[0].strip(), sender.split("<")[1].rstrip(">")
        self.add(to, {"id": gid, "thread_id": f"t{gid}", "labels": ["INBOX"], "headers": {},
                      "from_name": name, "from_email": addr, "reply_to": "", "subject": subject,
                      "rfc_message_id": f"<{gid}@x>", "references": "", "body": body})
        return gid

    def owner_sends(self, mailbox_address, thread_id, body):
        """The owner presses Send in Gmail (on our draft, possibly edited)."""
        for did, d in list(self.drafts.items()):
            if d["thread_id"] == thread_id:
                del self.drafts[did]  # Gmail turns the draft into a sent message
        self.add(mailbox_address, {"id": f"s{self.history + 1}", "thread_id": thread_id, "labels": ["SENT"],
                                   "headers": {}, "from_name": "Owner", "from_email": mailbox_address,
                                   "reply_to": "", "subject": "Re", "rfc_message_id": "", "references": "",
                                   "body": body})


G = FakeGmail()
gmail.exchange_code = lambda code: {"access_token": "at:" + code.split("|")[0], "refresh_token": "rt",
                                    "scope": code.split("|")[1] if "|" in code else gmail.MODIFY}
gmail.profile_with_token = lambda tok: {"emailAddress": tok.split(":", 1)[1], "historyId": str(G.history)}
gmail.access_token = lambda mb: "at"
gmail.revoke = lambda t: None
gmail.stop = lambda mb: None
gmail.new_message_ids = lambda mb, start: ([m["id"] for h, m in G.inbox.get(mb.email_address, []) if h > int(start)],
                                           str(G.history))
gmail.fetch = lambda mb, gid: next(m for _, m in G.inbox[mb.email_address] if m["id"] == gid)


def fake_send(mb, **kw):
    G.sent.append({"from": mb.email_address, **kw})
    G.history += 1
    sid = f"out{G.history}"
    G.add(mb.email_address, {"id": sid, "thread_id": kw.get("thread_id"), "labels": ["SENT"], "headers": {},
                             "from_name": "", "from_email": mb.email_address, "reply_to": "", "subject": "",
                             "rfc_message_id": "", "references": "", "body": kw["body"]})
    return {"id": sid}


def fake_create_draft(mb, **kw):
    did = f"d{G.next_draft}"
    G.next_draft += 1
    G.drafts[did] = {"mailbox": mb.email_address, **kw}
    return did


def fake_ensure_labels(mb):
    G.created_labels.append(mb.email_address)
    return {"green": "LG", "yellow": "LY", "red": "LR"}


gmail.send_reply = fake_send
gmail.create_draft = fake_create_draft
gmail.delete_draft = lambda mb, did: G.drafts.pop(did, None)
gmail.ensure_labels = fake_ensure_labels
gmail.set_color_label = lambda mb, ids, mid, color: G.labels.__setitem__(mid, color)

PINGS = []


def fake_push_send(sub, payload):
    PINGS.append((sub.endpoint, json.loads(payload)))
    return "gone" not in sub.endpoint


push._send = fake_push_send

from app import main  # noqa: E402  (after the patches: the graph is built with the canned nodes)


def token(org, user):
    now = int(time.time())
    claims = {"sub": user, "iat": now, "exp": now + 60, "azp": "http://localhost:3000", "v": 2,
              "o": {"id": org, "rol": "admin"}}
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="RS256")}


def connect(client, headers, code):
    url = client.post("/api/gmail/connect", headers=headers).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    return client.post("/api/gmail/callback", headers=headers, json={"code": code, "state": state})


def sync(client, headers):
    return client.post("/api/gmail/sync", headers=headers).json()


def msg(client, headers, gid):
    with main.SessionLocal() as s:
        mid = s.scalar(select(main.Message.id).where(main.Message.external_id == gid))
    return client.get(f"/api/messages/{mid}", headers=headers).json()


A, B = token("org_A", "user_a"), token("org_B", "user_b")
fails = 0


def check(name, cond):
    global fails
    print(("PASS " if cond else "FAIL ") + name)
    fails += not cond


with TestClient(main.app) as client:
    check("phone ping key offered", client.get("/api/push/key", headers=A).json()["key"] == "test-public")
    check("push subscribe needs login", client.post("/api/push/subscribe", json={}).status_code == 401)
    check("bad endpoint rejected", client.post("/api/push/subscribe", headers=A, json={
        "endpoint": "http://not-https.example/x", "p256dh": "k" * 20, "auth": "a" * 8}).status_code == 422)
    client.post("/api/push/subscribe", headers=A, json={"endpoint": "https://push.example/phone-a", "p256dh": "k" * 20, "auth": "a" * 8})
    client.post("/api/push/subscribe", headers=A, json={"endpoint": "https://push.example/gone-a", "p256dh": "k" * 20, "auth": "a" * 8})
    client.post("/api/push/subscribe", headers=B, json={"endpoint": "https://push.example/phone-b", "p256dh": "k" * 20, "auth": "a" * 8})
    check("device count per user", client.get("/api/push/key", headers=A).json()["devices"] == 2)

    st = connect(client, A, "alpha@gmail.com").json()
    check("new connection can draft (gmail.modify)", st["can_draft"] is True)
    check("B connects legacy (read+send only)",
          connect(client, B, f"beta@gmail.com|{' '.join(sorted(gmail.LEGACY_SCOPES))}").json()["can_draft"] is False)

    # 🟢 green: sent automatically, labeled green, no draft, no ping
    g1 = G.deliver("alpha@gmail.com", "Sara <sara@c.com>", "Hours", "When are you open?")
    sync(client, A)
    m1 = msg(client, A, g1)
    check("green sent automatically", m1["status"] == "sent_automatically" and len(G.sent) == 1)
    check("green thread labeled 'AI · Sent'", G.labels.get(g1) == "green")
    check("green: no draft, no ping", not G.drafts and not PINGS)

    # 🟡 yellow: draft in the thread + yellow label + ping to A's phone only
    g2 = G.deliver("alpha@gmail.com", "Mike <mike@c.com>", "Party", "Can we book for 40?")
    sync(client, A)
    m2 = msg(client, A, g2)
    d2 = [d for d in G.drafts.values() if d["thread_id"] == f"t{g2}"]
    check("yellow waits", m2["status"] == "waiting" and m2["color"] == "yellow")
    check("yellow draft is in the Gmail thread, to the customer", len(d2) == 1 and d2[0]["to"] == "mike@c.com"
          and d2[0]["in_reply_to"] == f"<{g2}@x>" and "Main Hall" in d2[0]["body"])
    check("yellow thread labeled 'AI · Needs approval'", G.labels.get(g2) == "yellow")
    pings_a = [p for e, p in PINGS if "-a" in e]
    check("ping went to A's devices", len(pings_a) == 2 and pings_a[0]["url"] == f"/m/{m2['id']}")
    check("ping is short: color + action + first name", pings_a[0]["title"] == "🟡 Approve reply to Mike" and pings_a[0]["body"] == "")
    check("yellow ping has Send / Decline", [a["action"] for a in pings_a[0]["actions"]] == ["approve", "reject"]
          and [a["title"] for a in pings_a[0]["actions"]] == ["Send", "Decline"])
    check("B's phone got nothing", not [e for e, _ in PINGS if "-b" in e])
    check("unsubscribed device was forgotten", client.get("/api/push/key", headers=A).json()["devices"] == 1)
    check("draft text never contains the color or reasons",
          all("yellow" not in d["body"].lower() and "approval" not in d["body"].lower() for d in G.drafts.values()))

    # approve in our app: sent once, draft removed, label -> green
    r = client.post(f"/api/messages/{m2['id']}/approve", headers=A, json={})
    check("approve in app sends", r.json()["status"] == "sent_after_approval" and len(G.sent) == 2)
    check("approve removed the Gmail draft", not [d for d in G.drafts.values() if d["thread_id"] == f"t{g2}"])
    check("approved thread relabeled green", G.labels.get(g2) == "green")
    sync(client, A)
    check("our own sent reply isn't mistaken for the owner's", len(G.sent) == 2 and msg(client, A, g2)["status"] == "sent_after_approval")
    check("approving twice is refused", client.post(f"/api/messages/{m2['id']}/approve", headers=A, json={}).status_code == 409)

    # approve by pressing Send in Gmail (edited): recorded, not sent again
    g3 = G.deliver("alpha@gmail.com", "Ann <ann@c.com>", "Booking", "We want to book for 40")
    sync(client, A)
    m3 = msg(client, A, g3)
    G.owner_sends("alpha@gmail.com", f"t{g3}", "Main Hall is yours for $750, just for you!")
    sent_before = len(G.sent)
    r = sync(client, A)
    m3 = msg(client, A, g3)
    check("sent-from-Gmail recorded as approved", m3["status"] == "sent_after_approval")
    check("…with the owner's edited text", m3["final_reply"].startswith("Main Hall is yours for $750"))
    check("…marked as edited (learning signal)", m3["was_edited"] is True)
    check("…and NOT sent a second time", len(G.sent) == sent_before)
    check("…thread relabeled green", G.labels.get(g3) == "green")

    # 🔴 complaint/refund: careful draft + red label
    g4 = G.deliver("alpha@gmail.com", "Lisa <lisa@c.com>", "Refund", "I want a refund now")
    sync(client, A)
    check("refund is red with a draft", msg(client, A, g4)["color"] == "red"
          and [d for d in G.drafts.values() if d["thread_id"] == f"t{g4}"] and G.labels.get(g4) == "red")
    check("red ping title", [p for _, p in PINGS][-1]["title"] == "🔴 Lisa needs you")
    check("red ping has no Send button", [p for _, p in PINGS][-1]["actions"] == [])

    # 🔴 wrong fact: NO draft left ready to send
    g5 = G.deliver("alpha@gmail.com", "Big <big@c.com>", "Big party", "Can we book for 120 people?")
    sync(client, A)
    m5 = msg(client, A, g5)
    check("wrong-fact draft is red", m5["color"] == "red" and any("120" in r for r in m5["reasons"]))
    check("…and NOT put in Gmail as a draft", not [d for d in G.drafts.values() if d["thread_id"] == f"t{g5}"])
    check("…but labeled red", G.labels.get(g5) == "red")

    # reject: draft removed, color removed
    r = client.post(f"/api/messages/{msg(client, A, g4)['id']}/reject", headers=A)
    check("reject", r.json()["status"] == "rejected")
    check("reject removed the draft and the color", not [d for d in G.drafts.values() if d["thread_id"] == f"t{g4}"]
          and G.labels.get(g4) is None)

    # Send / Decline tapped on the notification (no login: the one-time key is the permission)
    g7 = G.deliver("alpha@gmail.com", "Tom <tom@c.com>", "Party", "Can we book for 40?")
    sync(client, A)
    m7 = msg(client, A, g7)
    acts7 = {a["action"]: a["token"] for a in [p for e, p in PINGS if "-a" in e][-1]["actions"]}
    sent_before = len(G.sent)
    check("forged key refused", client.post("/api/push/act", json={"token": "x" * 20}).status_code == 401)
    r = client.post("/api/push/act", json={"token": acts7["approve"]})
    check("Send button sends", r.status_code == 200 and r.json()["status"] == "sent_after_approval"
          and len(G.sent) == sent_before + 1 and G.sent[-1]["body"].startswith("The Main Hall"))
    check("…removes the Gmail draft and relabels green", not [d for d in G.drafts.values() if d["thread_id"] == f"t{g7}"]
          and G.labels.get(g7) == "green")
    check("same key can't be used twice", client.post("/api/push/act", json={"token": acts7["approve"]}).status_code == 409
          and len(G.sent) == sent_before + 1)
    check("Decline after Send is refused too", client.post("/api/push/act", json={"token": acts7["reject"]}).status_code == 409)

    g8 = G.deliver("alpha@gmail.com", "Kim <kim@c.com>", "Party", "Can we book for 40?")
    sync(client, A)
    acts8 = {a["action"]: a["token"] for a in [p for e, p in PINGS if "-a" in e][-1]["actions"]}
    r = client.post("/api/push/act", json={"token": acts8["reject"]})
    check("Decline button declines, nothing sent", r.json()["status"] == "rejected" and len(G.sent) == sent_before + 1)
    check("…draft and color removed", not [d for d in G.drafts.values() if d["thread_id"] == f"t{g8}"]
          and G.labels.get(g8) is None)
    check("a key only works for its own email", acts7["approve"] != acts8["approve"])
    expired = jwt.encode({"m": m7["id"], "a": "approve", "exp": int(time.time()) - 10},
                         push._action_secret(), algorithm="HS256")
    check("expired key refused", client.post("/api/push/act", json={"token": expired}).status_code == 401)

    # legacy connection (no drafts permission): still works, no drafts/labels, ping still goes out
    g6 = G.deliver("beta@gmail.com", "Bob <bob@c.com>", "Party", "Can we book for 40?")
    sync(client, B)
    check("legacy mailbox still waits for approval", msg(client, B, g6)["status"] == "waiting")
    check("legacy: no draft, no label", not [d for d in G.drafts.values() if d["mailbox"] == "beta@gmail.com"]
          and g6 not in G.labels and "beta@gmail.com" not in G.created_labels)
    check("legacy: B's phone pinged", any("-b" in e for e, _ in PINGS))

    # isolation
    check("A can't open B's message", client.get(f"/api/messages/{msg(client, B, g6)['id']}", headers=A).status_code == 404)
    check("test ping only to my devices", client.post("/api/push/test", headers=A).json()["sent"] == 1)

main._pool.close()
from app.db import engine  # noqa: E402

engine.dispose()
with psycopg.connect(ADMIN_URL, autocommit=True) as c:
    c.execute("DROP DATABASE IF EXISTS drafttest WITH (FORCE)")
print(f"\n{'ALL PASSED' if not fails else f'{fails} FAILED'}")
sys.exit(1 if fails else 0)
