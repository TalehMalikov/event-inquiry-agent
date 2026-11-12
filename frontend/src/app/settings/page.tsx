"use client";

import { useEffect, useState } from "react";
import { api, Settings } from "@/lib/api";

const DESCRIPTIONS: Record<string, string> = {
  info: "Hours, parking, menu, general questions",
  inquiry: "Asking about hosting an event",
  booking: "Wants to confirm or reserve",
  other: "Anything else",
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.settings().then(setSettings).catch((e) => setError(e.message));
  }, []);

  function toggle(cat: string) {
    if (!settings) return;
    const on = settings.green_categories.includes(cat);
    setSettings({
      ...settings,
      green_categories: on ? settings.green_categories.filter((c) => c !== cat) : [...settings.green_categories, cat],
    });
    setSaved(false);
  }

  async function save() {
    setError(null);
    try {
      setSettings(await api.saveSettings(settings!));
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-slate-500">You decide how much the AI may do on its own.</p>
      </div>
      {error && <p className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
      {!settings ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : (
        <>
          {!settings.can_edit && (
            <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">
              Only your company&apos;s admins can change settings. You can still approve emails.
            </p>
          )}
          <section className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200 sm:p-5">
            <label className="text-sm font-semibold" htmlFor="company-name">Company name</label>
            <input id="company-name" value={settings.company_name}
              onChange={(e) => { setSettings({ ...settings, company_name: e.target.value }); setSaved(false); }}
              className="mt-2 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400" />
          </section>

          <section className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200 sm:p-5">
            <h2 className="font-semibold">Auto-send (green) categories</h2>
            <p className="text-xs text-slate-500">
              Emails in these categories go out without you, but only if the reply has no price, date, or promise.
              Everything else waits for your tap. Complaints and refunds always wait.
            </p>
            <ul className="mt-3 divide-y divide-slate-100">
              {settings.all_categories.map((cat) => {
                const on = settings.green_categories.includes(cat);
                return (
                  <li key={cat}>
                    <button onClick={() => toggle(cat)} className="flex w-full items-center gap-3 py-3 text-left">
                      <span className="flex-1">
                        <span className="block text-sm font-medium capitalize">{cat}</span>
                        <span className="block text-xs text-slate-500">{DESCRIPTIONS[cat]}</span>
                      </span>
                      <span role="switch" aria-checked={on}
                        className={`relative h-6 w-11 shrink-0 rounded-full transition ${on ? "bg-emerald-500" : "bg-slate-200"}`}>
                        <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${on ? "left-5" : "left-0.5"}`} />
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>

          <div className="flex items-center gap-3">
            <button onClick={save} className="rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white">
              Save settings
            </button>
            {saved && <span className="text-sm text-emerald-700">Saved.</span>}
          </div>
        </>
      )}
    </div>
  );
}
