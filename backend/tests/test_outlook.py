"""Outlook through the REAL agent graph and the REAL outlook.py: only the network (a fake Microsoft Graph) and the
two LLM calls are replaced. Scratch database "outlooktest".

    docker compose up -d db
    .venv/Scripts/python tests/test_outlook.py
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import psycopg  # noqa: E402

ADMIN_URL = "postgresql://inbox:inbox@localhost:5433/inbox"
with psycopg.connect(ADMIN_URL, autocommit=True) as c:
    c.execute("DROP DATABASE IF EXISTS outlooktest WITH (FORCE)")
    c.execute("CREATE DATABASE outlooktest")
from cryptography.fernet import Fernet  # noqa: E402

os.environ.update({
    "DATABASE_URL": "postgresql://inbox:inbox@localhost:5433/outlooktest",
    "CLERK_PUBLISHABLE_KEY": "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk", "CLERK_SECRET_KEY": "",
    "CLERK_AUTHORIZED_PARTIES": "http://localhost:3000", "DAILY_DRAFT_LIMIT": "50",
    "GOOGLE_CLIENT_ID": "", "GOOGLE_CLIENT_SECRET": "", "GOOGLE_PROJECT_ID": "", "GMAIL_PUBSUB_TOPIC": "",
    "MICROSOFT_CLIENT_ID": "ms-client", "MICROSOFT_CLIENT_SECRET": "ms-secret", "CRON_SECRET": "cron-secret",
    "MAILBOX_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    "VAPID_PUBLIC_KEY": "test-public", "VAPID_PRIVATE_KEY": "dGVzdA==",
})

import httpx  # noqa: E402
import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import agent, auth, gmail, outlook, push, rag  # noqa: E402

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
auth._jwks = lambda: type("J", (), {"get_signing_key_from_jwt": lambda self, t: type("K", (), {"key": KEY.public_key()})()})()
rag.try_embed = lambda texts: None


def fake_understand(state):
    body = state["email"].lower()
    cat, guests = ("inquiry", 120) if "120" in body else ("inquiry", 40) if "book" in body else ("info", None)
    return {"request": {"category": cat, "guests": guests, "weekend": True, "budget": None, "summary": body[:40]}}


def fake_draft(state):
    req = state["request"]
    if req["category"] == "info":
        d = dict(reply="We're open Tue-Sun, 11am to 11pm.", quoted_prices=[], offered_price=None, offered_guests=None,
                 commits_to_date=False, needs_team_check=False)
    elif req["guests"] == 120:
        d = dict(reply="Sure, we can host all 120 of you!", quoted_prices=[], offered_price=None, offered_guests=120,
                 commits_to_date=False, needs_team_check=False)
    else:
        d = dict(reply="The Main Hall fits 40, from $800 on Saturdays.\n\nBest,\nThe team", quoted_prices=[800],
                 offered_price=800, offered_guests=40, commits_to_date=False, needs_team_check=False)
    return {"draft": d}


agent.understand, agent.draft = fake_understand, fake_draft


# ---------- A fake Microsoft (login + Graph), answering the real HTTP calls outlook.py makes ----------

def ts(dt=None):
    return (dt or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeMicrosoft:
    def __init__(self):
        self.msgs = {}  # immutable id -> message
        self.categories = {}  # address -> {name: preset}
        self.n = 0
        self.refreshes = 0
        self.calls = []

    def new_id(self):
        self.n += 1
        return f"AAkALg-immutable-{self.n:04d}=="

    def deliver(self, to, name, sender, subject, body, *, when=None, headers=(), cats=()):
        mid = self.new_id()
        self.msgs[mid] = {"owner": to, "id": mid, "folder": "inbox", "conversationId": f"conv-{mid}",
                          "internetMessageId": f"<{mid}@cust>", "subject": subject, "isDraft": False,
                          "from": {"emailAddress": {"name": name, "address": sender}}, "replyTo": [],
                          "body": {"contentType": "text", "content": body}, "categories": list(cats),
                          "receivedDateTime": ts(when), "internetMessageHeaders": [{"name": k, "value": v}
                                                                                   for k, v in headers]}
        return mid

    def in_folder(self, folder, owner=None):
        return [m for m in self.msgs.values() if m["folder"] == folder and (owner is None or m["owner"] == owner)]

    def owner_sends_draft(self, conv):
        d = next(m for m in self.in_folder("drafts") if m["conversationId"] == conv)
        d.update(folder="sentitems", isDraft=False, sentDateTime=ts())
        return d

    def handle(self, method, url, headers=None, data=None, json=None, **_):
        self.calls.append((method, url))
        u = urlparse(url)
        if url == outlook.TOKEN_URL:
            if data["grant_type"] == "authorization_code":
                addr = data["code"]
                return httpx.Response(200, json={"access_token": f"at:{addr}", "refresh_token": f"rt:{addr}:0",
                                                 "expires_in": 3600,
                                                 "scope": "https://graph.microsoft.com/Mail.ReadWrite "
                                                          "https://graph.microsoft.com/Mail.Send User.Read "
                                                          "MailboxSettings.ReadWrite"})
            addr, n = data["refresh_token"][3:].rsplit(":", 1)
            self.refreshes += 1
            return httpx.Response(200, json={"access_token": f"at:{addr}", "refresh_token": f"rt:{addr}:{int(n) + 1}",
                                             "expires_in": 3600})
        assert headers["Authorization"].startswith("Bearer at:"), headers
        me = headers["Authorization"][len("Bearer at:"):]
        if "ImmutableId" not in headers.get("Prefer", "ImmutableId"):
            return httpx.Response(400, text="test wants immutable ids")
        path = u.path.removeprefix("/v1.0")
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        parts = path.strip("/").split("/")
        if path == "/me":
            return httpx.Response(200, json={"mail": None, "userPrincipalName": me.title()})
        if path == "/me/outlook/masterCategories":
            cats = self.categories.setdefault(me, {"VIP": "preset7"})
            if method == "POST":
                cats[json["displayName"]] = json["color"]
                return httpx.Response(201, json=json)
            return httpx.Response(200, json={"value": [{"displayName": k, "color": v} for k, v in cats.items()]})
        if parts[:2] == ["me", "mailFolders"]:
            field, since = q["$filter"].split(" ge ")
            rows = sorted((m for m in self.in_folder(parts[2], me) if m.get(field, "") >= since), key=lambda m: m[field])
            return httpx.Response(200, json={"value": [{"id": m["id"], field: m[field]} for m in rows[:int(q["$top"])]]})
        if parts[:2] == ["me", "messages"]:
            m = self.msgs.get(parts[2])
            if m is None or m["owner"] != me:
                return httpx.Response(404, json={"error": {"code": "ErrorItemNotFound"}})
            if len(parts) == 4 and parts[3] == "createReply":
                did = self.new_id()
                to = m["replyTo"] or [m["from"]]
                self.msgs[did] = {"owner": me, "id": did, "folder": "drafts", "conversationId": m["conversationId"],
                                  "subject": "RE: " + m["subject"], "isDraft": True, "toRecipients": to,
                                  "from": {"emailAddress": {"name": "Owner", "address": me}}, "categories": [],
                                  "body": {"contentType": "html", "content": "<p>quoted original</p>"},
                                  "internetMessageId": f"<{did}@owner>", "replyTo": []}
                return httpx.Response(201, json={"id": did})
            if len(parts) == 4 and parts[3] == "send":
                assert m["isDraft"]
                m.update(folder="sentitems", isDraft=False, sentDateTime=ts())
                return httpx.Response(202)
            if method == "PATCH":
                m.update(json)
                return httpx.Response(200, json=m)
            if method == "DELETE":
                del self.msgs[m["id"]]
                return httpx.Response(204)
            out = {k: m.get(k) for k in q.get("$select", "").split(",")} if "$select" in q else m
            if "outlook.body-content-type=\"text\"" not in headers.get("Prefer", "") and "body" in out:
                out["body"] = {"contentType": "html", "content": "<html>" + m["body"]["content"] + "</html>"}
            return httpx.Response(200, json=out)
        return httpx.Response(404, text=f"fake has no {method} {path}")


MS = FakeMicrosoft()
outlook._req = MS.handle

PINGS = []
push._send = lambda sub, payload: PINGS.append(json.loads(payload)) or True

from app import main  # noqa: E402
from app.db import Mailbox  # noqa: E402


def token(org, user):
    now = int(time.time())
    return {"Authorization": "Bearer " + jwt.encode({"sub": user, "iat": now, "exp": now + 60, "v": 2,
                                                     "azp": "http://localhost:3000", "o": {"id": org, "rol": "admin"}},
                                                    KEY, algorithm="RS256")}


A, B = token("org_A", "user_a"), token("org_B", "user_b")
fails = 0


def check(name, cond):
    global fails
    print(("PASS " if cond else "FAIL ") + name)
    fails += not cond


def sync(client, h):
    return client.post("/api/gmail/sync", headers=h).json()


def msg(client, h, ext_id):
    with main.SessionLocal() as s:
        mid = s.scalar(select(main.Message.id).where(main.Message.external_id == ext_id))
    return client.get(f"/api/messages/{mid}", headers=h).json() if mid else None


def drafts(conv):
    return [m for m in MS.in_folder("drafts") if m["conversationId"] == conv]


def sent(conv):
    return [m for m in MS.in_folder("sentitems") if m["conversationId"] == conv]


with TestClient(main.app) as client:
    client.post("/api/push/subscribe", headers=A, json={"endpoint": "https://push.example/a", "p256dh": "k" * 20,
                                                        "auth": "a" * 8})
    st = client.get("/api/gmail", headers=A).json()
    check("Settings offers Outlook (and not the unset Gmail)", st["available"] == {"gmail": False, "outlook": True})
    check("Gmail without keys: 503", client.post("/api/gmail/connect", headers=A).status_code == 503)
    check("unknown provider refused", client.post("/api/gmail/connect?provider=yahoo", headers=A).status_code == 400)

    url = client.post("/api/gmail/connect?provider=outlook", headers=A).json()["url"]
    q = parse_qs(urlparse(url).query)
    check("goes to Microsoft sign-in", url.startswith("https://login.microsoftonline.com/common/"))
    check("asks for read/draft + send + categories + offline",
          set(q["scope"][0].split()) == {"offline_access", "User.Read", "Mail.ReadWrite", "Mail.Send",
                                         "MailboxSettings.ReadWrite"})
    check("comes back to /outlook/callback", q["redirect_uri"][0].endswith("/outlook/callback"))
    state = q["state"][0]
    check("B can't finish A's sign-in", client.post("/api/gmail/callback", headers=B,
                                                    json={"code": "x@outlook.com", "state": state}).status_code == 400)

    old = MS.deliver("venue@outlook.com", "Old", "old@c.com", "Old", "Can we book for 40?",
                     when=datetime.now(timezone.utc) - timedelta(hours=2))
    r = client.post("/api/gmail/callback", headers=A, json={"code": "venue@outlook.com", "state": state})
    st = r.json()
    check("A connects venue@outlook.com", r.status_code == 200 and st["provider"] == "outlook"
          and st["email"] == "venue@outlook.com" and st["provider_name"] == "Outlook" and st["can_draft"] is True)
    with main.SessionLocal() as s:
        enc = s.scalar(select(Mailbox.refresh_token_enc))
    check("Microsoft token stored encrypted", "rt:" not in enc and gmail.decrypt(enc) == "rt:venue@outlook.com:0")

    # 🟢 green: sent automatically in the thread, green category, owner's own category kept
    g = MS.deliver("venue@outlook.com", "Sara Lee", "sara@c.com", "Hours", "When are you open?", cats=["VIP"])
    sync(client, A)
    check("email from before connecting is ignored", msg(client, A, old) is None)
    m = msg(client, A, g)
    out = sent(f"conv-{g}")
    check("green sent automatically", m["status"] == "sent_automatically" and len(out) == 1)
    check("…as an Outlook reply in the same thread, to the customer",
          out[0]["subject"] == "RE: Hours" and out[0]["toRecipients"][0]["emailAddress"]["address"] == "sara@c.com")
    check("…with our text only, as HTML (no quoted junk, no colors)",
          out[0]["body"]["contentType"] == "HTML" and "open Tue-Sun" in out[0]["body"]["content"]
          and "quoted original" not in out[0]["body"]["content"] and "green" not in out[0]["body"]["content"])
    check("three colored categories created", {k: v for k, v in MS.categories["venue@outlook.com"].items()} ==
          {"VIP": "preset7", "AI · Sent": "preset4", "AI · Needs approval": "preset3", "AI · Needs you": "preset0"})
    check("email gets green category, owner's VIP kept", MS.msgs[g]["categories"] == ["VIP", "AI · Sent"])
    check("no draft, no ping for green", not drafts(f"conv-{g}") and not PINGS)
    check("our own sent reply isn't treated as the owner's", sync(client, A)["new"] == 0)

    # 🟡 yellow: draft in the thread, yellow category, ping
    g2 = MS.deliver("venue@outlook.com", "Mike Ross", "mike@c.com", "Party", "Can we book for 40?")
    sync(client, A)
    m2 = msg(client, A, g2)
    d2 = drafts(f"conv-{g2}")
    check("yellow waits", m2["status"] == "waiting" and m2["color"] == "yellow")
    check("draft is in the Outlook thread, to Mike, with our text",
          len(d2) == 1 and d2[0]["toRecipients"][0]["emailAddress"]["address"] == "mike@c.com"
          and "Main Hall" in d2[0]["body"]["content"] and "<br>" in d2[0]["body"]["content"])
    check("yellow category on the email", MS.msgs[g2]["categories"] == ["AI · Needs approval"])
    check("phone ping", PINGS and PINGS[-1]["title"] == "🟡 Approve reply to Mike")

    # approve in the app: our draft itself is sent (updated text), nothing left behind
    r = client.post(f"/api/messages/{m2['id']}/approve", headers=A, json={"text": "Edited: Main Hall is yours."})
    out = sent(f"conv-{g2}")
    check("approve sends once", r.json()["status"] == "sent_after_approval" and len(out) == 1)
    check("…the draft itself, with the edited text", out[0]["id"] == d2[0]["id"]
          and "Edited: Main Hall" in out[0]["body"]["content"] and not drafts(f"conv-{g2}"))
    check("…category turns green", MS.msgs[g2]["categories"] == ["AI · Sent"])
    with main.SessionLocal() as s:
        row = s.scalar(select(main.Message).where(main.Message.external_id == g2))
    check("…the sent email is remembered, the draft id cleared", row.sent_external_id == d2[0]["id"]
          and row.draft_external_id is None)
    check("the sent copy is never deleted", d2[0]["id"] in MS.msgs)

    # approve by pressing Send in Outlook: recorded, the sent email is NOT deleted
    g3 = MS.deliver("venue@outlook.com", "Kim", "kim@c.com", "Party", "Can we book for 40?")
    sync(client, A)
    owner_sent = MS.owner_sends_draft(f"conv-{g3}")
    owner_sent["body"]["content"] = "Yes Kim, see you Saturday!"
    sync(client, A)
    m3 = msg(client, A, g3)
    check("sent-from-Outlook recorded as approved", m3["status"] == "sent_after_approval"
          and "see you Saturday" in (m3["final_reply"] or ""))
    check("…not sent a second time", len(sent(f"conv-{g3}")) == 1)
    check("…and the owner's sent email still exists", owner_sent["id"] in MS.msgs)
    check("…category turns green", MS.msgs[g3]["categories"] == ["AI · Sent"])

    # Decline: draft removed, color removed, nothing sent
    g4 = MS.deliver("venue@outlook.com", "Tom", "tom@c.com", "Party", "Can we book for 40?")
    sync(client, A)
    m4 = msg(client, A, g4)
    client.post(f"/api/messages/{m4['id']}/reject", headers=A)
    check("decline: no draft, no color, nothing sent", not drafts(f"conv-{g4}") and MS.msgs[g4]["categories"] == []
          and not sent(f"conv-{g4}"))

    # 🔴 red because the draft is wrong (120 guests): no ready-to-send draft
    g5 = MS.deliver("venue@outlook.com", "Ana", "ana@c.com", "Wedding", "Can we book for 120 people?")
    sync(client, A)
    check("red: needs you, red category, no draft", msg(client, A, g5)["color"] == "red"
          and MS.msgs[g5]["categories"] == ["AI · Needs you"] and not drafts(f"conv-{g5}"))

    # several emails in the same second, checked twice: each answered exactly once
    same = [MS.deliver("venue@outlook.com", f"C{i}", f"c{i}@x.org", "Hi", "When are you open?") for i in range(3)]
    sync(client, A)
    MS.deliver("venue@outlook.com", "C9", "c9@x.org", "Hi", "When are you open?")
    sync(client, A)
    sync(client, A)
    with main.SessionLocal() as s:
        n_same = [s.scalar(select(main.Message.id).where(main.Message.external_id == x)) for x in same]
    check("same-second emails each processed once", all(n_same) and
          all(len(sent(f"conv-{x}")) == 1 for x in same))

    MS.deliver("venue@outlook.com", "News", "news@shop.com", "Sale", "50% off",
               headers=[("List-Unsubscribe", "<mailto:u@shop.com>")])
    MS.deliver("venue@outlook.com", "Bank", "noreply@bank.com", "Statement", "Your statement")
    before = len(MS.in_folder("sentitems"))
    sync(client, A)
    check("newsletters and no-reply senders ignored", len(MS.in_folder("sentitems")) == before)

    with main.SessionLocal() as s:
        enc = s.scalar(select(Mailbox.refresh_token_enc))
    check("Microsoft's fresh refresh token was saved", gmail.decrypt(enc) != "rt:venue@outlook.com:0"
          and MS.refreshes >= 1)

    # isolation: B can't see A's Outlook emails or take the address
    check("B sees none of A's emails", client.get("/api/messages", headers=B).json() == [])
    url_b = client.post("/api/gmail/connect?provider=outlook", headers=B).json()["url"]
    r = client.post("/api/gmail/callback", headers=B,
                    json={"code": "venue@outlook.com", "state": parse_qs(urlparse(url_b).query)["state"][0]})
    check("B can't connect A's Outlook address", r.status_code == 409)

    # cron covers Outlook too
    g6 = MS.deliver("venue@outlook.com", "Lia", "lia@c.com", "Hours", "When are you open?")
    r = client.get("/api/cron/gmail", headers={"Authorization": "Bearer cron-secret"})
    check("scheduled check answers Outlook mail", r.status_code == 200 and len(sent(f"conv-{g6}")) == 1)

    r = client.delete("/api/gmail", headers=A)
    check("disconnect", r.json()["connected"] is False)

print("\nALL PASSED" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
