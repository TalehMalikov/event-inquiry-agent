"use client";

import { useCallback, useEffect, useState } from "react";
import MessageCard from "@/components/MessageCard";
import SimulateEmail from "@/components/SimulateEmail";
import { api, Message } from "@/lib/api";

type Tab = "needs_you" | "handled" | "all";
const NEEDS_YOU = new Set(["waiting", "processing", "error"]);

export default function InboxPage() {
  const [messages, setMessages] = useState<Message[] | null>(null);
  const [tab, setTab] = useState<Tab>("needs_you");
  const [error, setError] = useState<string | null>(null);

  // Bumping this number triggers a refresh (after sending, approving, etc.)
  const [refreshKey, setRefreshKey] = useState(0);
  const load = useCallback(() => setRefreshKey((k) => k + 1), []);

  // Poll the server: every 2s while the AI is drafting, every 15s otherwise.
  const processing = messages?.some((m) => m.status === "processing");
  useEffect(() => {
    let alive = true;
    const fetchMessages = () =>
      api
        .messages()
        .then((m) => {
          if (!alive) return;
          setMessages(m);
          setError(null);
        })
        .catch((e) => alive && setError(`Can't reach the server: ${(e as Error).message}`));
    fetchMessages();
    const t = setInterval(fetchMessages, processing ? 2000 : 15000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [processing, refreshKey]);

  const list = (messages ?? []).filter((m) =>
    tab === "all" ? true : tab === "needs_you" ? NEEDS_YOU.has(m.status) : !NEEDS_YOU.has(m.status),
  );
  const needsYou = messages?.filter((m) => NEEDS_YOU.has(m.status)).length ?? 0;
  const red = messages?.filter((m) => m.status === "waiting" && m.color === "red").length ?? 0;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Inbox</h1>
        <p className="text-sm text-slate-500">
          {needsYou === 0
            ? "You're all caught up."
            : `${needsYou} need${needsYou === 1 ? "s" : ""} you${red ? `, ${red} red` : ""}.`}
        </p>
      </div>

      <SimulateEmail onSent={load} />

      <div className="flex gap-1 rounded-xl bg-slate-200/60 p-1 text-sm">
        {(
          [
            ["needs_you", `Needs you${needsYou ? ` (${needsYou})` : ""}`],
            ["handled", "Handled"],
            ["all", "All"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex-1 rounded-lg py-1.5 font-medium transition ${
              tab === key ? "bg-white shadow-sm" : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {error && <p className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
      {messages === null && !error && <p className="text-sm text-slate-400">Loading…</p>}
      {messages !== null && list.length === 0 && (
        <p className="py-10 text-center text-sm text-slate-400">
          {tab === "needs_you" ? "Nothing waiting for you. 🎉" : "No emails here yet."}
        </p>
      )}

      <div className="space-y-3">
        {list.map((m) => (
          // key includes status so the card resets when a draft arrives or a decision is made
          <MessageCard key={`${m.id}-${m.status}`} message={m} onChange={load} />
        ))}
      </div>
    </div>
  );
}
