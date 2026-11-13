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
  { id: "system", label: "System" },
  { id: "agent", label: "AI agent" },
  { id: "db", label: "Database" },
  { id: "stack", label: "Services" },
];

// A tapped card lights up with everything it talks to
function around(id: string, links: Link[]): Highlight {
  const l = links.filter((x) => x.from === id || x.to === id);
  return { nodes: new Set([id, ...l.map((x) => x.from), ...l.map((x) => x.to)]), links: new Set(l.map((x) => x.id)) };
}

const panel = "rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200";

function Details({ info, onClose }: { info: Info; onClose: () => void }) {
  return (
    <div className={panel}>
      <div className="flex items-center gap-3">
        <span className="text-2xl" aria-hidden>
          {info.icon}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold leading-tight">{info.title}</h3>
          <p className="text-xs text-slate-500">{info.tech}</p>
        </div>
        <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-700" aria-label="Close">
          ✕
        </button>
      </div>
      <p className="mt-3 text-sm text-slate-700">{info.what}</p>
      {info.code && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {info.code.map((c) => (
            <code key={c} className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500">
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
  const last = flow ? flow.steps.length - 1 : 0;

  useEffect(() => {
    if (!playing || !flow) return;
    const t = setTimeout(() => (step >= last ? setPlaying(false) : setStep(step + 1)), 2200);
    return () => clearTimeout(t);
  }, [playing, step, flow, last, setStep]);

  return (
    <div className={panel}>
      <h3 className="text-sm font-semibold">Play a flow</h3>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {FLOWS.map((f) => (
          <button
            key={f.id}
            onClick={() => {
              const on = f.id !== flowId;
              setFlowId(on ? f.id : null);
              setStep(0);
              setPlaying(on);
            }}
            className={`rounded-full px-3 py-1.5 text-[13px] transition ${
              f.id === flowId ? "bg-slate-900 text-white" : "bg-slate-100 hover:bg-slate-200"
            }`}
          >
            {f.title}
          </button>
        ))}
      </div>
      {flow && (
        <div className="mt-4">
          <p className="min-h-[2.5rem] text-[15px] font-medium leading-snug">
            <span className="mr-1.5 text-slate-400">
              {step + 1}/{flow.steps.length}
            </span>
            {flow.steps[step].text}
          </p>
          <div className="mt-2 flex gap-1">
            {flow.steps.map((_, i) => (
              <button
                key={i}
                onClick={() => {
                  setStep(i);
                  setPlaying(false);
                }}
                className={`h-1.5 flex-1 rounded-full transition ${i <= step ? "bg-slate-900" : "bg-slate-200"}`}
                aria-label={`Step ${i + 1}`}
              />
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <button
              onClick={() => {
                setStep(Math.max(0, step - 1));
                setPlaying(false);
              }}
              disabled={step === 0}
              className="rounded-xl border border-slate-200 px-3 py-1.5 text-sm disabled:opacity-40"
              aria-label="Back"
            >
              ←
            </button>
            <button
              onClick={() => {
                if (step >= last) setStep(0);
                setPlaying(!playing || step >= last);
              }}
              className="flex-1 rounded-xl bg-slate-900 px-3 py-1.5 text-sm font-semibold text-white"
            >
              {playing && step < last ? "Pause" : step >= last ? "Replay" : "▶ Play"}
            </button>
            <button
              onClick={() => {
                setStep(Math.min(last, step + 1));
                setPlaying(false);
              }}
              disabled={step >= last}
              className="rounded-xl border border-slate-200 px-3 py-1.5 text-sm disabled:opacity-40"
              aria-label="Next"
            >
              →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const ALL_INFO: Record<string, Info> = Object.fromEntries([...SYSTEM_ITEMS, ...AGENT_ITEMS].map((i) => [i.id, i]));
const TABLE_INFO: Record<string, Info> = Object.fromEntries(
  TABLES.map((t) => [t.id, { title: t.title, tech: "Table", icon: "🗄️", kind: "data" as const, what: t.note }]),
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

  function select(id: string | null) {
    setSelected(id);
    if (id) setFlowId(null); // tapping a card takes over from a playing flow
  }

  return (
    // Wider than the app's normal column: diagrams need room
    <div className="relative left-1/2 w-[calc(100vw-2rem)] max-w-[1400px] -translate-x-1/2">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold tracking-tight">Architecture</h1>
        <div className="flex gap-1 rounded-2xl bg-white p-1 shadow-sm ring-1 ring-slate-200">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => {
                setTab(t.id);
                setSelected(null);
              }}
              className={`rounded-xl px-3.5 py-1.5 text-sm font-medium transition ${
                tab === t.id ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === "stack" ? (
        <div className="grid gap-4 md:grid-cols-[1fr_320px]">
          <section className={panel}>
            <h2 className="font-semibold">Services</h2>
            <ul className="mt-2 divide-y divide-slate-100 text-sm">
              {STACK.map((s) => (
                <li key={s.name} className="flex items-center gap-3 py-2">
                  <span className="w-36 shrink-0 font-medium">{s.name}</span>
                  <span className="flex-1 text-slate-600">{s.role}</span>
                  <span className="shrink-0 text-xs text-slate-400">{s.plan}</span>
                </li>
              ))}
            </ul>
          </section>
          <section className={panel}>
            <h2 className="font-semibold">Not used</h2>
            <ul className="mt-2 divide-y divide-slate-100 text-sm">
              {NOT_USED.map((n) => (
                <li key={n.name} className="py-2">
                  <span className="font-medium">{n.name}</span> <span className="text-slate-500">· {n.why}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
          <div className="min-w-0">
            {/* key: each tab gets its own fresh diagram */}
            <Diagram
              key={tab}
              items={tab === "system" ? SYSTEM_ITEMS : tab === "agent" ? AGENT_ITEMS : undefined}
              boxes={tab === "system" ? SYSTEM_BOXES : undefined}
              tables={tab === "db" ? TABLES : undefined}
              links={links}
              highlight={highlight}
              selected={selected}
              onSelect={select}
              height={tab === "system" ? undefined : "h-[55vh] min-h-[380px]"}
            />
            <p className="mt-2 text-xs text-slate-400">Tap a card · pinch to zoom · two fingers to move · drag cards</p>
          </div>
          <aside className="space-y-4">
            {info && <Details info={info} onClose={() => setSelected(null)} />}
            {tab === "system" && <FlowPlayer flowId={flowId} setFlowId={setFlowId} step={step} setStep={setStep} />}
            {tab === "agent" && !info && (
              <div className={`${panel} space-y-2 text-sm`}>
                <h3 className="font-semibold">Traffic light</h3>
                <p>🟢 Info only → sent</p>
                <p>🟡 Price, date, missing fact → owner approves</p>
                <p>🔴 Complaint, refund, wrong fact → owner decides</p>
                <p className="pt-1 text-xs text-slate-400">AI writes. Plain code decides.</p>
              </div>
            )}
            {tab === "db" && !info && (
              <div className={`${panel} text-sm`}>
                <h3 className="font-semibold">One Postgres database</h3>
                <p className="mt-2 text-slate-600">Every row belongs to one company. Tokens are encrypted.</p>
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
