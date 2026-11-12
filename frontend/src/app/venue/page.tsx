"use client";

import { useEffect, useState } from "react";
import { api, Policy, Room } from "@/lib/api";

const EMPTY_ROOM: Room = { name: "", capacity: 10, weekday_min: 0, weekend_min: 0 };

export default function VenuePage() {
  const [rooms, setRooms] = useState<Room[] | null>(null);
  const [policies, setPolicies] = useState<Policy[] | null>(null);
  const [newPolicy, setNewPolicy] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.rooms(), api.policies()])
      .then(([r, p]) => {
        setRooms(r);
        setPolicies(p);
      })
      .catch((e) => setError(e.message));
  }, []);

  function update(i: number, field: keyof Room, value: string) {
    setRooms((rs) =>
      rs!.map((r, j) => (j === i ? { ...r, [field]: field === "name" ? value : Number(value) || 0 } : r)),
    );
    setStatus(null);
  }

  async function saveRooms() {
    setError(null);
    try {
      setRooms(await api.saveRooms(rooms!.filter((r) => r.name.trim())));
      setStatus("Saved. The AI uses these numbers on the next email.");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function addPolicy() {
    setError(null);
    try {
      setPolicies(await api.addPolicy(newPolicy.trim()));
      setNewPolicy("");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function deletePolicy(id: number) {
    setError(null);
    try {
      setPolicies(await api.deletePolicy(id));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const cell = "w-full rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm outline-none focus:border-slate-400";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Venue data</h1>
        <p className="text-sm text-slate-500">
          The AI answers only from these facts. Change a number here and the next reply uses it.
        </p>
      </div>
      {error && <p className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}

      <section className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200 sm:p-5">
        <h2 className="font-semibold">Rooms & prices</h2>
        <p className="text-xs text-slate-500">Stored in the database and looked up exactly, so prices are never guessed.</p>
        {rooms === null ? (
          <p className="mt-3 text-sm text-slate-400">Loading…</p>
        ) : (
          <div className="mt-3 space-y-3">
            <div className="hidden grid-cols-[2fr_1fr_1fr_1fr_auto] gap-2 text-xs font-medium text-slate-500 sm:grid">
              <span>Room</span>
              <span>Max guests</span>
              <span>Weekday min $</span>
              <span>Weekend min $</span>
              <span className="w-8" />
            </div>
            {rooms.map((r, i) => (
              <div key={i} className="grid grid-cols-3 gap-2 sm:grid-cols-[2fr_1fr_1fr_1fr_auto]">
                <input className={`${cell} col-span-3 sm:col-span-1`} placeholder="Room name" value={r.name}
                  onChange={(e) => update(i, "name", e.target.value)} />
                <input className={cell} type="number" aria-label="Max guests" value={r.capacity}
                  onChange={(e) => update(i, "capacity", e.target.value)} />
                <input className={cell} type="number" aria-label="Weekday minimum" value={r.weekday_min}
                  onChange={(e) => update(i, "weekday_min", e.target.value)} />
                <input className={cell} type="number" aria-label="Weekend minimum" value={r.weekend_min}
                  onChange={(e) => update(i, "weekend_min", e.target.value)} />
                <button onClick={() => setRooms(rooms.filter((_, j) => j !== i))}
                  className="col-span-3 w-full rounded-lg text-xs text-slate-400 hover:text-rose-600 sm:col-span-1 sm:w-8"
                  aria-label="Remove room">
                  ✕
                </button>
              </div>
            ))}
            <div className="flex flex-wrap items-center gap-2">
              <button onClick={() => setRooms([...rooms, { ...EMPTY_ROOM }])}
                className="rounded-lg px-3 py-1.5 text-sm text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50">
                + Add room
              </button>
              <button onClick={saveRooms} className="rounded-lg bg-slate-900 px-4 py-1.5 text-sm font-semibold text-white">
                Save
              </button>
              {status && <span className="text-sm text-emerald-700">{status}</span>}
            </div>
          </div>
        )}
      </section>

      <section className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200 sm:p-5">
        <h2 className="font-semibold">Policies & FAQs</h2>
        <p className="text-xs text-slate-500">Searched by meaning (RAG). The AI gets the most relevant ones for each email.</p>
        <ul className="mt-3 divide-y divide-slate-100">
          {(policies ?? []).map((p) => (
            <li key={p.id} className="flex items-start gap-3 py-2 text-sm">
              <span className="flex-1">{p.text}</span>
              {!p.indexed && (
                <span className="text-xs text-amber-600" title="Not embedded yet (check API key)">not indexed</span>
              )}
              <button onClick={() => deletePolicy(p.id)} className="text-xs text-slate-400 hover:text-rose-600"
                aria-label="Delete policy">
                ✕
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-3 flex gap-2">
          <input className={cell} placeholder="e.g. Pets: dogs are welcome on the patio." value={newPolicy}
            onChange={(e) => setNewPolicy(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && newPolicy.trim().length >= 3 && addPolicy()} />
          <button onClick={addPolicy} disabled={newPolicy.trim().length < 3}
            className="shrink-0 rounded-lg bg-slate-900 px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-50">
            Add
          </button>
        </div>
      </section>
    </div>
  );
}
