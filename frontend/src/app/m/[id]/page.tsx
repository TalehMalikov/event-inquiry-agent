"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import MessageCard from "@/components/MessageCard";
import { api, Message } from "@/lib/api";

// Opened from a phone notification: one email, its color and reasons, Approve / Edit / Reject.
export default function MessagePage() {
  const { id } = useParams<{ id: string }>();
  const [m, setM] = useState<Message | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const reload = useCallback(() => setRefresh((k) => k + 1), []);

  useEffect(() => {
    api
      .message(Number(id))
      .then(setM)
      .catch((e) => setError((e as Error).message));
  }, [id, refresh]);

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm font-medium text-slate-500 hover:text-slate-800">
        ← Inbox
      </Link>
      {error && <p className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
      {!m && !error && <p className="text-sm text-slate-400">Loading…</p>}
      {m && <MessageCard key={`${m.id}-${m.status}`} message={m} onChange={reload} />}
    </div>
  );
}
