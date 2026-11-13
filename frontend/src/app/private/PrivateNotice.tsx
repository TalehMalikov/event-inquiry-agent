"use client";

import { useAuth } from "@clerk/nextjs";

export default function PrivateNotice() {
  const { userId } = useAuth();
  return (
    <div className="mx-auto mt-16 max-w-sm text-center">
      <p className="text-3xl" aria-hidden>
        🔒
      </p>
      <h1 className="mt-2 font-semibold">This page is private</h1>
      {userId && <p className="mt-4 select-all font-mono text-xs text-slate-400">{userId}</p>}
    </div>
  );
}
