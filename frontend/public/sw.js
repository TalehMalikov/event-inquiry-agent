// Service worker: shows "🟡 Mike: Party" pings with Send / Decline, and opens the email in the app.

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

// Pages tell us whether they run as the installed app, so a tap opens the app instead of a browser tab.
const appWindows = new Set();
self.addEventListener("message", (event) => {
  if (event.data?.type === "hello" && event.source) {
    if (event.data.standalone) appWindows.add(event.source.id);
    else appWindows.delete(event.source.id);
  }
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: event.data ? event.data.text() : "Needs you" };
  }
  const actions = (data.actions || []).map((a) => ({ action: a.action, title: a.title }));
  const tokens = Object.fromEntries((data.actions || []).map((a) => [a.action, a.token]));
  event.waitUntil(
    self.registration.showNotification(data.title || "Needs you", {
      body: data.body || "", // kept empty: the title already says color + who + what
      badge: "/badge-96.png", // small status-bar E; no large icon on purpose
      tag: data.tag || undefined, // the same email replaces its old ping instead of stacking
      renotify: Boolean(data.tag),
      actions,
      data: { url: data.url || "/", tokens },
    }),
  );
});

async function openInApp(path) {
  const url = new URL(path || "/", self.location.origin).href;
  const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  const app = windows.find((w) => appWindows.has(w.id));
  if (app) {
    await app.focus();
    return app.navigate(url);
  }
  return self.clients.openWindow(url); // with the app installed, this opens the app itself
}

async function act(action, data) {
  try {
    const res = await fetch("/api/push/act", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: data.tokens[action] }),
    });
    if (!res.ok) throw new Error(String(res.status));
    const out = await res.json();
    await self.registration.showNotification(action === "approve" ? `✓ Sent to ${out.who}` : `Declined`, {
      tag: "done",
      badge: "/badge-96.png",
      silent: true,
    });
    // Waiting inside waitUntil keeps the worker alive long enough to tidy up the confirmation
    await new Promise((r) => setTimeout(r, 4000));
    (await self.registration.getNotifications({ tag: "done" })).forEach((x) => x.close());
  } catch {
    // Expired, already handled, or offline: open the email so the owner can decide there.
    await openInApp(data.url);
  }
}

self.addEventListener("notificationclick", (event) => {
  const data = event.notification.data || {};
  event.notification.close();
  if (event.action === "approve" || event.action === "reject") {
    event.waitUntil(act(event.action, data));
  } else {
    event.waitUntil(openInApp(data.url));
  }
});
