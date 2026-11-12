"use client";

import { useEffect, useState } from "react";

// Chrome/Edge/Samsung fire this when the site can be installed. A tiny script in layout.tsx catches it
// at page start (window.__installPrompt), because it often fires before this component exists.
type InstallEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: "accepted" | "dismissed" }> };
type InstallWindow = Window & { __installPrompt?: InstallEvent | null };

type Mode = "hidden" | "button" | "ios";
const DISMISSED = "install-banner-dismissed";

/** "Install app" button, so pings come from the app ("Inbox AI") instead of from "Chrome".
 *  banner = small dismissible strip for the inbox; otherwise a card for Settings. */
export default function InstallApp({ banner = false }: { banner?: boolean }) {
  const [mode, setMode] = useState<Mode>("hidden");
  const [prompt, setPrompt] = useState<InstallEvent | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    const installed =
      window.matchMedia("(display-mode: standalone)").matches ||
      (navigator as Navigator & { standalone?: boolean }).standalone === true;
    if (installed || (banner && localStorage.getItem(DISMISSED))) return;
    const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- install support is only known in the browser
    if (ios) setMode("ios");
    const pick = () => {
      const saved = (window as InstallWindow).__installPrompt;
      if (saved) {
        setPrompt(saved);
        setMode("button");
      }
    };
    pick(); // it may already have arrived (e.g. right after a reload)
    const onInstalled = () => {
      setDone(true);
      setMode("hidden");
    };
    window.addEventListener("installpromptready", pick);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("installpromptready", pick);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, [banner]);

  async function install() {
    if (!prompt) return;
    await prompt.prompt();
    (window as InstallWindow).__installPrompt = null; // Chrome allows each announcement to be used once
    if ((await prompt.userChoice).outcome === "accepted") setMode("hidden");
    setPrompt(null);
  }

  function dismiss() {
    localStorage.setItem(DISMISSED, "1");
    setMode("hidden");
  }

  if (done && !banner) {
    return <p className="text-sm text-emerald-700">Installed. Open Inbox AI from your home screen.</p>;
  }
  if (mode === "hidden") return null;

  const text =
    mode === "button"
      ? "Install the app: notifications then come from Inbox AI, not from your browser."
      : "On iPhone: tap Share, then “Add to Home Screen”, and open Inbox AI from there to get notifications.";

  if (banner) {
    return (
      <div className="flex items-center gap-3 rounded-2xl bg-slate-900 px-4 py-3 text-sm text-white">
        <span className="flex-1">📲 {text}</span>
        {mode === "button" && (
          <button onClick={install} className="shrink-0 rounded-lg bg-white px-3 py-1.5 font-semibold text-slate-900">
            Install
          </button>
        )}
        <button onClick={dismiss} aria-label="Dismiss" className="shrink-0 px-1 text-slate-400 hover:text-white">
          ✕
        </button>
      </div>
    );
  }
  return (
    <div className="rounded-xl bg-slate-50 p-3 text-sm text-slate-700">
      <p>{text}</p>
      {mode === "button" && (
        <button onClick={install}
          className="mt-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white">
          Install app
        </button>
      )}
    </div>
  );
}
