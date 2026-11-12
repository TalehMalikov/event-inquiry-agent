"use client";

import { useEffect, useState } from "react";
import { api, PushSub } from "@/lib/api";

type Support = "loading" | "ok" | "ios-install" | "unsupported" | "denied";

function b64ToBytes(b64: string) {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

function toSub(s: PushSubscription): PushSub {
  const j = s.toJSON();
  return { endpoint: s.endpoint, p256dh: j.keys?.p256dh ?? "", auth: j.keys?.auth ?? "" };
}

function detect(): Support {
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const installed = window.matchMedia("(display-mode: standalone)").matches;
  if (ios && !installed) return "ios-install"; // iPhone: notifications only work from the Home Screen app
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) return "unsupported";
  if (Notification.permission === "denied") return "denied";
  return "ok";
}

// Settings card: "🟡 Mike: Party for 40" pings on this phone/computer when an email needs you.
export default function Notifications() {
  const [support, setSupport] = useState<Support>("loading");
  const [sub, setSub] = useState<PushSubscription | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    const s = detect();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- browser capabilities are only known on the client
    setSupport(s);
    if (s !== "ok") return;
    navigator.serviceWorker
      .register("/sw.js")
      .then((reg) => reg.pushManager.getSubscription())
      .then((existing) => {
        setSub(existing);
        if (existing) api.pushSubscribe(toSub(existing)).catch(() => {}); // keep it tied to this company
      })
      .catch(() => setSupport("unsupported"));
  }, []);

  async function enable() {
    setBusy(true);
    setNote(null);
    try {
      const { key } = await api.pushKey();
      if (!key) throw new Error("Notifications aren't set up on the server yet");
      if ((await Notification.requestPermission()) !== "granted") {
        setSupport("denied");
        return;
      }
      const reg = await navigator.serviceWorker.register("/sw.js");
      await navigator.serviceWorker.ready;
      const s = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(key) });
      await api.pushSubscribe(toSub(s));
      setSub(s);
      setNote("On. You'll get a ping when an email needs you.");
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function disable() {
    if (!sub) return;
    setBusy(true);
    try {
      await api.pushUnsubscribe(toSub(sub)).catch(() => {});
      await sub.unsubscribe();
      setSub(null);
      setNote("Off on this device.");
    } finally {
      setBusy(false);
    }
  }

  async function test() {
    setBusy(true);
    try {
      const r = await api.pushTest();
      setNote(r.sent ? "Test sent. It should pop up in a few seconds." : "No device to send to. Turn notifications on first.");
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200 sm:p-5">
      <h2 className="font-semibold">Phone notifications</h2>
      <p className="text-xs text-slate-500">
        A ping like “🟡 Mike: Party for 40” when an email needs you. Tap it to approve in one screen. Green emails
        never ping you.
      </p>

      {support === "loading" && <p className="mt-3 text-sm text-slate-400">Checking this device…</p>}

      {support === "ios-install" && (
        <ol className="mt-3 list-decimal space-y-1 rounded-xl bg-slate-50 p-3 pl-8 text-sm text-slate-700">
          <li>In Safari, tap the <b>Share</b> button (square with an arrow).</li>
          <li>
            Choose <b>Add to Home Screen</b>, then <b>Add</b>.
          </li>
          <li>Open the app from your Home Screen and come back to Settings to turn notifications on.</li>
        </ol>
      )}

      {support === "unsupported" && (
        <p className="mt-3 text-sm text-slate-500">This browser can&apos;t show notifications. Try Chrome, Edge, or Safari.</p>
      )}

      {support === "denied" && (
        <p className="mt-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-800">
          Notifications are blocked for this site. Allow them in your browser or phone settings, then reload.
        </p>
      )}

      {support === "ok" && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {sub ? (
            <>
              <span className="flex items-center gap-2 text-sm">
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" /> On for this device
              </span>
              <button onClick={test} disabled={busy}
                className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium disabled:opacity-50">
                Send a test
              </button>
              <button onClick={disable} disabled={busy}
                className="rounded-xl px-4 py-2 text-sm font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-50">
                Turn off
              </button>
            </>
          ) : (
            <button onClick={enable} disabled={busy}
              className="rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-50">
              {busy ? "Turning on…" : "Turn on notifications"}
            </button>
          )}
        </div>
      )}
      {note && <p className="mt-2 text-sm text-slate-600">{note}</p>}
    </section>
  );
}
