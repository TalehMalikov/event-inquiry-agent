"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, MailStatus } from "@/lib/api";

// Top of the inbox: which mailbox the AI is watching, plus a manual "check now".
export default function MailboxBar({ onNewMail }: { onNewMail: () => void }) {
  const [mail, setMail] = useState<MailStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    api.gmail().then(setMail).catch(() => {});
  }, []);

  // Without instant push, check Gmail every 15 seconds while this page is open and visible
  // (a background job also checks every 15 minutes when nobody has the app open).
  const autoCheck = mail?.connected && !mail.instant;
  const inFlight = useRef(false); // a check that finds new mail also drafts it (~10 s): never overlap
  useEffect(() => {
    if (!autoCheck) return;
    const t = setInterval(() => {
      if (document.visibilityState !== "visible" || inFlight.current) return;
      inFlight.current = true;
      api
        .syncGmail()
        .then((r) => {
          setMail(r);
          if (r.new) onNewMail();
        })
        .catch(() => {})
        .finally(() => {
          inFlight.current = false;
        });
    }, 15_000);
    return () => clearInterval(t);
  }, [autoCheck, onNewMail]);

  async function check() {
    setBusy(true);
    setNote(null);
    try {
      const r = await api.syncGmail();
      setMail(r);
      setNote(r.new ? `${r.new} new email${r.new === 1 ? "" : "s"}` : "No new emails");
      if (r.new) onNewMail();
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!mail) return null;
  if (!mail.connected) {
    return (
      <Link
        href="/settings"
        className="block rounded-2xl border-2 border-dashed border-slate-200 px-4 py-3 text-sm text-slate-600 hover:border-slate-300"
      >
        📧 No inbox connected yet. <span className="font-semibold underline">Connect Gmail in Settings</span> so the AI
        can read and answer your emails.
      </Link>
    );
  }
  return (
    <div className="flex items-center gap-3 rounded-2xl bg-white px-4 py-3 text-sm shadow-sm ring-1 ring-slate-200">
      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${mail.status === "ok" ? "bg-emerald-500" : "bg-rose-500"}`} />
      <span className="flex-1 truncate">
        Watching <span className="font-medium">{mail.email}</span>
        {mail.status !== "ok" && <span className="text-rose-600"> · needs attention (see Settings)</span>}
        {note && <span className="text-slate-500"> · {note}</span>}
      </span>
      <button
        onClick={check}
        disabled={busy}
        className="shrink-0 rounded-lg px-3 py-1.5 font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-50"
      >
        {busy ? "Checking…" : "Check now"}
      </button>
    </div>
  );
}
