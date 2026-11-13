"use client";

import { useEffect, useState } from "react";
import { api, MailStatus } from "@/lib/api";

type Provider = "gmail" | "outlook";
const NAMES: Record<Provider, string> = { gmail: "Gmail", outlook: "Outlook" };

// Settings card: connect / disconnect the company's inbox (Gmail or Outlook).
export default function GmailConnection({ canEdit }: { canEdit: boolean }) {
  const [mail, setMail] = useState<MailStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.gmail().then(setMail).catch((e) => setError((e as Error).message));
  }, []);

  async function connect(provider: Provider) {
    setBusy(true);
    setError(null);
    try {
      const { url } = await api.connectGmail(provider);
      window.location.assign(url); // Google's or Microsoft's sign-in page, then back to /gmail|outlook/callback
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  async function disconnect() {
    if (!confirm(`Disconnect ${mail?.email}? The AI stops reading and answering this inbox.`)) return;
    setBusy(true);
    try {
      setMail(await api.disconnectGmail());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200 sm:p-5">
      <h2 className="font-semibold">Email inbox</h2>
      <p className="text-xs text-slate-500">
        The AI reads new emails in this inbox and replies from it. Replies that need you wait as a draft in the
        email thread, with a colored label (Gmail) or category (Outlook), so you can just press Send there. It
        never deletes your mail.
        Newsletters, promotions and automatic emails are ignored.
      </p>
      {error && <p className="mt-3 rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
      {!mail ? (
        <p className="mt-3 text-sm text-slate-400">Loading…</p>
      ) : mail.connected ? (
        <div className="mt-3 space-y-3">
          <div className="flex items-center gap-3 rounded-xl bg-slate-50 p-3">
            <span className={`h-2.5 w-2.5 rounded-full ${mail.status === "ok" ? "bg-emerald-500" : "bg-rose-500"}`} />
            <div className="flex-1 text-sm">
              <div className="font-medium">{mail.email}</div>
              <div className="text-xs text-slate-500">
                {mail.provider_name ?? "Gmail"} · {mail.status === "ok" ? "connected" : "needs attention"}
                {mail.last_synced_at && ` · last checked ${new Date(mail.last_synced_at).toLocaleString()}`}
              </div>
            </div>
          </div>
          {mail.last_error && <p className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{mail.last_error}</p>}
          {mail.can_draft === false && (
            <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">
              Click <b>Reconnect</b> once to let the AI put drafts and colored labels in your Gmail.
            </p>
          )}
          {canEdit && (
            <div className="flex gap-2">
              <button
                onClick={() => connect(mail.provider ?? "gmail")}
                disabled={busy}
                className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium disabled:opacity-50"
              >
                Reconnect
              </button>
              <button
                onClick={disconnect}
                disabled={busy}
                className="rounded-xl px-4 py-2 text-sm font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-50"
              >
                Disconnect
              </button>
            </div>
          )}
        </div>
      ) : !mail.configured ? (
        <p className="mt-3 text-sm text-amber-700">Email is not set up on the server yet.</p>
      ) : canEdit ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {(["gmail", "outlook"] as Provider[])
            .filter((p) => mail.available?.[p] ?? p === "gmail")
            .map((p) => (
              <button
                key={p}
                onClick={() => connect(p)}
                disabled={busy}
                className="rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
              >
                Connect {NAMES[p]}
              </button>
            ))}
          {busy && <span className="self-center text-sm text-slate-500">Opening sign-in…</span>}
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-500">No inbox connected yet. Ask a company admin to connect one.</p>
      )}
    </section>
  );
}
