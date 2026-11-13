"use client";

import { useEffect, useMemo, useState } from "react";
import Diagram, { type Highlight } from "./Diagram";
import {
  AGENT_ITEMS,
  AGENT_LINKS,
  FLOWS,
  NOT_USED,
  STACK,
  SYSTEM_BOXES,
  SYSTEM_ITEMS,
  SYSTEM_LINKS,
  TABLES,
  TABLE_LINKS,
  type Info,
  type Link,
} from "./data";

type Tab = "system" | "agent" | "db" | "stack";
const TABS: { id: Tab; label: string }[] = [
  { id: "system", label: "System map" },
  { id: "agent", label: "AI agent" },
  { id: "db", label: "Database" },
  { id: "stack", label: "Services & choices" },
];

// A clicked node lights up with everything it talks to
function around(id: string, links: Link[]): Highlight {
  const l = links.filter((x) => x.from === id || x.to === id);
  return { nodes: new Set([id, ...l.map((x) => x.from), ...l.map((x) => x.to)]), links: new Set(l.map((x) => x.id)) };
}

function Details({ info, onClose }: { info: Info; onClose: () => void }) {
  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <div className="flex items-start gap-3">
        <span className="text-2xl" aria-hidden>
          {info.icon}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold leading-tight">{info.title}</h3>
          <p className="text-xs text-slate-500">{info.tech}</p>
        </div>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-700" aria-label="Close">
          ✕
        </button>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-slate-700">{info.what}</p>
      {info.facts && (
        <ul className="mt-3 space-y-1 text-sm text-slate-600">
          {info.facts.map((f) => (
            <li key={f} className="flex gap-2">
              <span className="text-slate-400">•</span>
              {f}
            </li>
          ))}
        </ul>
      )}
      {info.code && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {info.code.map((c) => (
            <code key={c} className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">
              {c}
            </code>
          ))}
        </div>
      )}
    </div>
  );
}

function FlowPlayer({
  flowId,
  setFlowId,
  step,
  setStep,
}: {
  flowId: string | null;
  setFlowId: (id: string | null) => void;
  step: number;
  setStep: (n: number) => void;
}) {
  const [playing, setPlaying] = useState(false);
  const flow = FLOWS.find((f) => f.id === flowId);

  useEffect(() => {
    if (!playing || !flow) return;
    if (step >= flow.steps.length - 1) {
      const t = setTimeout(() => setPlaying(false), 0);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setStep(step + 1), 3200);
    return () => clearTimeout(t);
  }, [playing, step, flow, setStep]);

  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <h3 className="text-sm font-semibold">Follow a flow</h3>
      <p className="text-xs text-slate-500">Pick one and step through it; the map lights up each step.</p>
      <div className="mt-3 flex flex-col gap-1.5">
        {FLOWS.map((f) => (
          <button
            key={f.id}
            onClick={() => {
              setFlowId(f.id === flowId ? null : f.id);
              setStep(0);
              setPlaying(false);
            }}
            className={`rounded-xl px-3 py-2 text-left text-sm transition ${
              f.id === flowId ? "bg-slate-900 text-white" : "bg-slate-50 hover:bg-slate-100"
            }`}
          >
            {f.title}
          </button>
        ))}
      </div>
      {flow && (
        <div className="mt-4">
          <p className="text-xs text-slate-500">{flow.summary}</p>
          <ol className="mt-3 space-y-1.5">
            {flow.steps.map((s, i) => (
              <li key={i}>
                <button
                  onClick={() => {
                    setStep(i);
                    setPlaying(false);
                  }}
                  className={`flex w-full gap-2 rounded-lg p-2 text-left text-[13px] leading-snug transition ${
                    i === step ? "bg-amber-50 text-slate-900 ring-1 ring-amber-300" : "text-slate-500 hover:bg-slate-50"
                  }`}
                >
                  <span
                    className={`mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
                      i === step ? "bg-slate-900 text-white" : "bg-slate-200 text-slate-600"
                    }`}
                  >
                    {i + 1}
                  </span>
                  {s.text}
                </button>
              </li>
            ))}
          </ol>
          <div className="mt-3 flex gap-2">
            <button
              onClick={() => setStep(Math.max(0, step - 1))}
              disabled={step === 0}
              className="rounded-xl border border-slate-200 px-3 py-1.5 text-sm disabled:opacity-40"
            >
              ← Back
            </button>
            <button
              onClick={() => {
                if (step >= flow.steps.length - 1) setStep(0);
                setPlaying(!playing);
              }}
              className="flex-1 rounded-xl bg-slate-900 px-3 py-1.5 text-sm font-semibold text-white"
            >
              {playing ? "Pause" : step >= flow.steps.length - 1 ? "Replay" : "▶ Play"}
            </button>
            <button
              onClick={() => setStep(Math.min(flow.steps.length - 1, step + 1))}
              disabled={step >= flow.steps.length - 1}
              className="rounded-xl border border-slate-200 px-3 py-1.5 text-sm disabled:opacity-40"
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Legend() {
  const rows = [
    ["bg-zinc-900", "Our code on Vercel"],
    ["bg-teal-500", "AI"],
    ["bg-sky-500", "Data"],
    ["bg-indigo-500", "Outside service"],
    ["bg-slate-500", "People / devices"],
  ];
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
      {rows.map(([c, t]) => (
        <span key={t} className="flex items-center gap-1.5">
          <span className={`h-2.5 w-2.5 rounded-sm ${c}`} />
          {t}
        </span>
      ))}
      <span className="flex items-center gap-1.5">
        <span className="h-0 w-5 border-t-2 border-dashed border-slate-400" />
        Built, switched off
      </span>
      <span>· Drag boxes, pinch or scroll to zoom, tap anything for details</span>
    </div>
  );
}

const ALL_INFO: Record<string, Info> = Object.fromEntries(
  [...SYSTEM_ITEMS, ...AGENT_ITEMS].map((i) => [i.id, i]),
);
const TABLE_INFO: Record<string, Info> = Object.fromEntries(
  TABLES.map((t) => [
    t.id,
    { title: t.title, tech: t.note, icon: "🗄️", kind: "data" as const, what: t.cols.join(" · ") },
  ]),
);

export default function Architecture() {
  const [tab, setTab] = useState<Tab>("system");
  const [selected, setSelected] = useState<string | null>(null);
  const [flowId, setFlowId] = useState<string | null>(null);
  const [step, setStep] = useState(0);

  const links = tab === "agent" ? AGENT_LINKS : tab === "db" ? TABLE_LINKS : SYSTEM_LINKS;
  const flow = FLOWS.find((f) => f.id === flowId);

  const highlight: Highlight = useMemo(() => {
    if (tab === "system" && flow) {
      const s = flow.steps[Math.min(step, flow.steps.length - 1)];
      return { nodes: new Set(s.nodes), links: new Set(s.links) };
    }
    return selected ? around(selected, links) : null;
  }, [tab, flow, step, selected, links]);

  const info = selected ? (tab === "db" ? TABLE_INFO[selected] : ALL_INFO[selected]) : null;

  function switchTab(t: Tab) {
    setTab(t);
    setSelected(null);
  }

  return (
    // Wider than the app's normal column: diagrams need room
    <div className="relative left-1/2 w-[calc(100vw-2rem)] max-w-[1400px] -translate-x-1/2">
      <header className="mb-4">
        <h1 className="text-2xl font-semibold tracking-tight">How Event Inquiry Agent is built</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          An AI assistant for event venues: it reads the company inbox (Gmail or Outlook), drafts every reply from the
          company&apos;s own facts, and a traffic light decides: 🟢 send now, 🟡 wait for approval, 🔴 the owner must
          look. Many companies, each with its own inbox, data and rules.
        </p>
      </header>

      <div className="mb-4 flex gap-1 overflow-x-auto rounded-2xl bg-white p-1 shadow-sm ring-1 ring-slate-200">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => switchTab(t.id)}
            className={`shrink-0 rounded-xl px-4 py-2 text-sm font-medium transition ${
              tab === t.id ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "stack" ? (
        <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
          <section className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
            <h2 className="px-4 pt-4 font-semibold">Services used</h2>
            <div className="overflow-x-auto">
              <table className="mt-2 w-full text-sm">
                <thead className="text-left text-xs uppercase tracking-wide text-slate-400">
                  <tr>
                    <th className="px-4 py-2">Service</th>
                    <th className="px-4 py-2">What it does here</th>
                    <th className="px-4 py-2">Plan</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {STACK.map((s) => (
                    <tr key={s.name}>
                      <td className="whitespace-nowrap px-4 py-2.5 font-medium">{s.name}</td>
                      <td className="px-4 py-2.5 text-slate-600">{s.role}</td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-slate-500">{s.plan}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
            <h2 className="font-semibold">Considered, not used (yet)</h2>
            <ul className="mt-3 space-y-3">
              {NOT_USED.map((n) => (
                <li key={n.name} className="text-sm">
                  <div className="font-medium">{n.name}</div>
                  <div className="text-slate-600">{n.why}</div>
                </li>
              ))}
            </ul>
          </section>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
          <div className="min-w-0 space-y-2">
            {/* key: each tab gets its own fresh diagram (positions reset when switching) */}
            <Diagram
              key={tab}
              items={tab === "system" ? SYSTEM_ITEMS : tab === "agent" ? AGENT_ITEMS : undefined}
              boxes={tab === "system" ? SYSTEM_BOXES : undefined}
              tables={tab === "db" ? TABLES : undefined}
              links={links}
              highlight={highlight}
              selected={selected}
              onSelect={setSelected}
              height={tab === "system" ? undefined : "h-[56vh] min-h-[420px]"}
            />
            <Legend />
          </div>
          <aside className="space-y-4">
            {info && <Details info={info} onClose={() => setSelected(null)} />}
            {tab === "system" && <FlowPlayer flowId={flowId} setFlowId={setFlowId} step={step} setStep={setStep} />}
            {tab === "agent" && !info && (
              <div className="rounded-2xl bg-white p-4 text-sm text-slate-600 shadow-sm ring-1 ring-slate-200">
                <h3 className="font-semibold text-slate-900">The traffic light</h3>
                <p className="mt-2">Every email gets a draft. Only two steps use AI (💬); the decision itself is plain code.</p>
                <ul className="mt-3 space-y-2">
                  <li>🟢 <b>Green</b>: informational, no price, date or promise, and the category is on the owner&apos;s auto-send list → sent right away.</li>
                  <li>🟡 <b>Yellow</b>: a price, a date commitment, a missing fact → draft waits, phone ping with Send / Decline.</li>
                  <li>🔴 <b>Red</b>: complaint or refund, or the draft states something wrong (too many guests, price below minimum) → the owner must look.</li>
                </ul>
                <p className="mt-3 text-xs text-slate-500">Tap a step in the diagram to see what it does.</p>
              </div>
            )}
            {tab === "db" && !info && (
              <div className="rounded-2xl bg-white p-4 text-sm text-slate-600 shadow-sm ring-1 ring-slate-200">
                <h3 className="font-semibold text-slate-900">One Postgres database (Neon)</h3>
                <p className="mt-2">
                  Every row belongs to one company (<code>company_id</code>), and the backend filters every query by the
                  company in the login token. Vectors (pgvector) and paused agent runs (LangGraph checkpoints) live in
                  the same database, so there is one thing to back up and secure.
                </p>
                <p className="mt-2">Mailbox tokens are encrypted before they are stored.</p>
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
