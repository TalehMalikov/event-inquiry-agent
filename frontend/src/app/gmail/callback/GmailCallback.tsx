"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

export default function GmailCallback() {
  const params = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false); // Google's code works only once, so never send it twice

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const code = params.get("code");
    const state = params.get("state");
    if (params.get("error") || !code || !state) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time result of reading the URL
      setError(params.get("error") === "access_denied" ? "You cancelled the Gmail sign-in." : "Gmail sign-in failed.");
      return;
    }
    api
      .finishGmail(code, state)
      .then(() => router.replace("/"))
      .catch((e) => setError((e as Error).message));
  }, [params, router]);

  return (
    <div className="mx-auto mt-16 max-w-sm text-center">
      {error ? (
        <>
          <p className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>
          <Link href="/settings" className="mt-4 inline-block text-sm font-semibold underline">
            Back to Settings
          </Link>
        </>
      ) : (
        <p className="text-sm text-slate-500">Connecting Gmail…</p>
      )}
    </div>
  );
}
