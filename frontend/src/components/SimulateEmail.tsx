"use client";

import { useState } from "react";
import { api } from "@/lib/api";

const SAMPLES = [
  {
    label: "Hours & parking",
    from_name: "Maya Chen",
    from_email: "maya@example.com",
    subject: "Sunday hours?",
    body: "Hi! What time do you open on Sunday, and is there parking nearby?",
  },
  {
    label: "80 people for $500",
    from_name: "Jordan Ellis",
    from_email: "jordan@acme.example",
    subject: "Company party this Saturday",
    body: "Hey, can you host 80 people this Saturday for $500? It's for our company party.",
  },
  {
    label: "Patio birthday",
    from_name: "Priya Patel",
    from_email: "priya@example.com",
    subject: "Birthday on the patio",
    body: "Hello, we'd like the patio for about 20 people next Wednesday for a birthday. Can we bring our own cake? What would it cost?",
  },
  {
    label: "Complaint + refund",
    from_name: "Sam Rivera",
    from_email: "sam@example.com",
    subject: "Very disappointed",
    body: "We had dinner at your place last Friday. The food was cold and we waited an hour. I want a refund.",
  },
];

const EMPTY = { from_name: "", from_email: "", subject: "", body: "" };

export default function SimulateEmail({ onSent }: { onSent: () => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.simulate({
        from_name: form.from_name || "Customer",
        from_email: form.from_email || "customer@example.com",
        subject: form.subject || "Event inquiry",
        body: form.body,
      });
      setForm(EMPTY);
      setOpen(false);
      onSent();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="w-full rounded-2xl border-2 border-dashed border-slate-200 px-4 py-3 text-sm font-medium text-slate-500 transition hover:border-slate-300 hover:text-slate-700"
      >
        + Simulate an incoming email
      </button>
    );
  }

  const input = "w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-slate-400";

  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Simulate an incoming email</h2>
        <button onClick={() => setOpen(false)} className="text-sm text-slate-400 hover:text-slate-600">
          Close
        </button>
      </div>
      <p className="mt-1 text-xs text-slate-500">Until a real inbox is connected, emails arrive here.</p>

      <div className="mt-3 flex flex-wrap gap-2">
        {SAMPLES.map(({ label, ...s }) => (
          <button
            key={label}
            onClick={() => setForm(s)}
            className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600 hover:bg-slate-200"
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <input className={input} placeholder="Name" value={form.from_name}
          onChange={(e) => setForm({ ...form, from_name: e.target.value })} />
        <input className={input} placeholder="Email" value={form.from_email}
          onChange={(e) => setForm({ ...form, from_email: e.target.value })} />
        <input className={`${input} sm:col-span-2`} placeholder="Subject" value={form.subject}
          onChange={(e) => setForm({ ...form, subject: e.target.value })} />
        <textarea className={`${input} sm:col-span-2`} rows={4} placeholder="Message" value={form.body}
          onChange={(e) => setForm({ ...form, body: e.target.value })} />
      </div>
      {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}
      <button
        onClick={submit}
        disabled={busy || !form.body.trim()}
        className="mt-3 w-full rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
      >
        {busy ? "Sending…" : "Receive email"}
      </button>
    </div>
  );
}
