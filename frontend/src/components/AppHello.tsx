"use client";

import { useEffect } from "react";

// Tells the notification worker whether this window is the installed app, so tapping a ping opens the app
// (not a browser tab). Also makes sure the worker is registered on every device that installed the app.
export default function AppHello() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    const standalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      (navigator as Navigator & { standalone?: boolean }).standalone === true;
    const hello = () => navigator.serviceWorker.controller?.postMessage({ type: "hello", standalone });
    navigator.serviceWorker.register("/sw.js").then(() => navigator.serviceWorker.ready).then(hello).catch(() => {});
    navigator.serviceWorker.addEventListener("controllerchange", hello);
    return () => navigator.serviceWorker.removeEventListener("controllerchange", hello);
  }, []);
  return null;
}
