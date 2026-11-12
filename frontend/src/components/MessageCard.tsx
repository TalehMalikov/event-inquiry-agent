"use client";

import { useState } from "react";
import { api, COLOR_STYLES, Message, STATUS_LABELS, timeAgo } from "@/lib/api";

export default function MessageCard({ message: m, onChange }: { message: Message; onChange: () => void }) {
  const [text, setText] = useState(m.draft ?? "");
  const [busy, setBusy] = useState<null | "approve" | "reject" | "retry">(null);
  const [error, setError] = useState<string | null>(null);
  const [showDetails, setShowDetails] = useState(false);

  const style = m.color ? COLOR_STYLES[m.color] : null;
  const waiting = m.status === "waiting";
  const edited = text.trim() !== (m.draft ?? "").trim();

  async function act(kind: "approve" | "reject" | "retry") {
    setBusy(kind);
    setError(null);
    try {
      if (kind === "approve") await api.approve(m.id, text);
      else if (kind === "reject") await api.reject(m.id);
      else await api.retry(m.id);
      onChange();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const claims = m.claims ?? {};
  const chips: string[] = [];
  if (claims.offered_guests) chips.push(`👥 ${claims.offered_guests} guests`);
  if (claims.offered_price) chips.push(`💲${claims.offered_price.toLocaleString()}`);
  if (claims.commits_to_date) chips.push("📅 commits to a date");
  if (claims.needs_team_check) chips.push("❓ missing a fact");

  return (
    <article className={`rounded-2xl bg-white p-4 shadow-sm ring-1 ${style?.ring ?? "ring-slate-200"} sm:p-5`}>
      <div className="flex items-start gap-3">
        <span
          className={`mt-1.5 h-3 w-3 shrink-0 rounded-full ${
            style?.dot ?? (m.status === "error" ? "bg-slate-400" : "animate-pulse bg-slate-300")
          }`}
          aria-label={style?.label ?? m.status}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3">
            <h3 className="truncate font-semibold">{m.from_name}</h3>
            <span className="text-xs text-slate-400">{timeAgo(m.received_at)}</span>
          </div>
          <p className="truncate text-sm text-slate-500">{m.subject}</p>
          {m.summary && <p className="mt-1 text-sm">{m.summary}</p>}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
        <span className={`rounded-full px-2.5 py-1 font-medium ${style?.chip ?? "bg-slate-100 text-slate-600"}`}>
          {STATUS_LABELS[m.status]}
        </span>
        {m.category && <span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-600">{m.category}</span>}
        {chips.map((c) => (
          <span key={c} className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-600">
            {c}
          </span>
        ))}
      </div>
      {m.reasons.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-slate-500">
          {m.reasons.map((r) => (
            <li key={r}>• {r}</li>
          ))}
        </ul>
      )}

      {m.status === "processing" && <p className="mt-4 text-sm text-slate-400">Reading, looking up facts, drafting…</p>}

      {m.status === "error" && (
        <div className="mt-4 rounded-xl bg-slate-50 p-3 text-sm">
          <p className="text-rose-600">{m.error}</p>
          <button
            onClick={() => act("retry")}
            disabled={!!busy}
            className="mt-2 rounded-lg bg-slate-900 px-3 py-1.5 text-white disabled:opacity-50"
          >
            {busy === "retry" ? "Retrying…" : "Retry"}
          </button>
        </div>
      )}

      {waiting && (
        <div className="mt-4">
          <label className="text-xs font-medium text-slate-500" htmlFor={`draft-${m.id}`}>
            AI draft {edited && <span className="text-amber-600">(edited)</span>}
          </label>
          <textarea
            id={`draft-${m.id}`}
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={8}
            className="mt-1 w-full resize-y rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm leading-relaxed outline-none focus:border-slate-400 focus:bg-white"
          />
          <div className="mt-3 flex gap-2">
            <button
              onClick={() => act("approve")}
              disabled={!!busy || !text.trim()}
              className="flex-1 rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-50 sm:flex-none"
            >
              {busy === "approve" ? "Sending…" : edited ? "Send edited reply" : "Approve & send"}
            </button>
            <button
              onClick={() => act("reject")}
              disabled={!!busy}
              className="rounded-xl px-4 py-3 text-sm font-medium text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50 disabled:opacity-50"
            >
              {busy === "reject" ? "…" : "Reject"}
            </button>
          </div>
        </div>
      )}

      {m.final_reply && !waiting && (
        <div className="mt-4 whitespace-pre-wrap rounded-xl bg-slate-50 p-3 text-sm leading-relaxed text-slate-700">
          {m.final_reply}
        </div>
      )}

      {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}

      {m.status !== "processing" && (
        <button
          onClick={() => setShowDetails((v) => !v)}
          className="mt-3 text-xs font-medium text-slate-400 hover:text-slate-600"
        >
          {showDetails ? "Hide details" : "Show email & facts used"}
        </button>
      )}
      {showDetails && (
        <div className="mt-2 space-y-3 rounded-xl bg-slate-50 p-3 text-xs text-slate-600">
          <div>
            <p className="font-semibold text-slate-700">Customer email</p>
            <p className="mt-1 whitespace-pre-wrap">{m.body}</p>
            <p className="mt-1 text-slate-400">{m.from_email}</p>
          </div>
          {!!m.facts.rooms?.length && (
            <div>
              <p className="font-semibold text-slate-700">Rooms (from database)</p>
              {m.facts.rooms.map((r) => (
                <p key={r.name}>
                  {r.name}: up to {r.capacity} guests, ${r.weekday_min} weekdays / ${r.weekend_min} weekends
                </p>
              ))}
            </div>
          )}
          {!!m.facts.policies?.length && (
            <div>
              <p className="font-semibold text-slate-700">Policies (from RAG)</p>
              {m.facts.policies.map((p) => (
                <p key={p}>• {p}</p>
              ))}
            </div>
          )}
        </div>
      )}
    </article>
  );
}
