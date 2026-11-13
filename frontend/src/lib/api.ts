export type Color = "green" | "yellow" | "red";
export type Status =
  | "processing"
  | "sending"
  | "waiting"
  | "sent_automatically"
  | "sent_after_approval"
  | "rejected"
  | "error";

export type Room = {
  id?: number;
  name: string;
  capacity: number;
  weekday_min: number;
  weekend_min: number;
};

export type Message = {
  id: number;
  from_name: string;
  from_email: string;
  subject: string;
  body: string;
  received_at: string;
  category: string | null;
  summary: string | null;
  color: Color | null;
  reasons: string[];
  claims: {
    quoted_prices?: number[];
    offered_price?: number | null;
    offered_guests?: number | null;
    commits_to_date?: boolean;
    needs_team_check?: boolean;
  };
  facts: { rooms?: Room[]; policies?: string[]; request?: Record<string, unknown> };
  draft: string | null;
  final_reply: string | null;
  status: Status;
  error: string | null;
  was_edited: boolean | null;
  decided_at: string | null;
};

export type Policy = { id: number; text: string; indexed: boolean };
export type Settings = {
  company_name: string;
  green_categories: string[];
  all_categories: string[];
  can_edit: boolean;
};

type ClerkWindow = Window & { Clerk?: { session?: { getToken: () => Promise<string | null> } | null } };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Clerk's short-lived session token says who you are and which company you're working in.
  const token = await (window as ClerkWindow).Clerk?.session?.getToken();
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (res.status === 401 || res.status === 403) {
    // Not signed in, or no company chosen yet. Runs outside React, so a hard redirect is intended.
    const to = res.status === 401 ? "/sign-in" : "/choose-company";
    let detail = "";
    try {
      detail = (await res.clone().json()).detail;
    } catch {}
    if (res.status === 401 || detail.startsWith("Choose")) {
      window.location.href = to;
      throw new Error(res.status === 401 ? "Please sign in" : "Choose a company first");
    }
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export type MailStatus = {
  connected: boolean;
  configured: boolean;
  available?: { gmail: boolean; outlook: boolean }; // which providers the server has keys for
  provider?: "gmail" | "outlook";
  provider_name?: string;
  email?: string;
  status?: "ok" | "error";
  last_error?: string | null;
  last_synced_at?: string | null;
  watch_expires_at?: string | null;
  instant?: boolean; // true = Gmail push (seconds); false = checked every 15 s while open, every 15 min otherwise
  can_draft?: boolean; // false = connected before drafts/labels existed: Reconnect to enable them
};

export type PushSub = { endpoint: string; p256dh: string; auth: string };

export const api = {
  gmail: () => request<MailStatus>("/gmail"),
  connectGmail: (provider: "gmail" | "outlook" = "gmail") =>
    request<{ url: string }>(`/gmail/connect?provider=${provider}`, { method: "POST" }),
  finishGmail: (code: string, state: string) =>
    request<MailStatus>("/gmail/callback", { method: "POST", body: JSON.stringify({ code, state }) }),
  disconnectGmail: () => request<MailStatus>("/gmail", { method: "DELETE" }),
  syncGmail: () => request<MailStatus & { new: number }>("/gmail/sync", { method: "POST" }),
  messages: () => request<Message[]>("/messages"),
  message: (id: number) => request<Message>(`/messages/${id}`),
  pushKey: () => request<{ key: string | null; devices: number }>("/push/key"),
  pushSubscribe: (s: PushSub) => request<{ ok: boolean }>("/push/subscribe", { method: "POST", body: JSON.stringify(s) }),
  pushUnsubscribe: (s: PushSub) =>
    request<{ ok: boolean }>("/push/unsubscribe", { method: "POST", body: JSON.stringify(s) }),
  pushTest: () => request<{ sent: number }>("/push/test", { method: "POST" }),
  approve: (id: number, text: string) =>
    request<Message>(`/messages/${id}/approve`, { method: "POST", body: JSON.stringify({ text }) }),
  reject: (id: number) => request<Message>(`/messages/${id}/reject`, { method: "POST" }),
  retry: (id: number) => request<{ ok: boolean }>(`/messages/${id}/retry`, { method: "POST" }),
  rooms: () => request<Room[]>("/rooms"),
  saveRooms: (rooms: Room[]) => request<Room[]>("/rooms", { method: "PUT", body: JSON.stringify(rooms) }),
  policies: () => request<Policy[]>("/policies"),
  addPolicy: (text: string) => request<Policy[]>("/policies", { method: "POST", body: JSON.stringify({ text }) }),
  deletePolicy: (id: number) => request<Policy[]>(`/policies/${id}`, { method: "DELETE" }),
  settings: () => request<Settings>("/settings"),
  saveSettings: (s: { company_name: string; green_categories: string[] }) =>
    request<Settings>("/settings", { method: "PUT", body: JSON.stringify(s) }),
};

export const COLOR_STYLES: Record<Color, { dot: string; chip: string; label: string; ring: string }> = {
  green: { dot: "bg-emerald-500", chip: "bg-emerald-50 text-emerald-700", label: "Green", ring: "ring-emerald-200" },
  yellow: { dot: "bg-amber-400", chip: "bg-amber-50 text-amber-800", label: "Yellow", ring: "ring-amber-200" },
  red: { dot: "bg-rose-500", chip: "bg-rose-50 text-rose-700", label: "Red", ring: "ring-rose-200" },
};

export const STATUS_LABELS: Record<Status, string> = {
  processing: "AI is drafting…",
  sending: "Sending…",
  waiting: "Waiting for you",
  sent_automatically: "Sent automatically",
  sent_after_approval: "Sent after your approval",
  rejected: "Rejected, not sent",
  error: "Something went wrong",
};

export function timeAgo(iso: string) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
}
