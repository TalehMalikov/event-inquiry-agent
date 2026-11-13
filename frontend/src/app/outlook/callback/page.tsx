import { Suspense } from "react";
import GmailCallback from "../../gmail/callback/GmailCallback";

// Microsoft sends the owner back here after "Connect Outlook".
export default function Page() {
  return (
    <Suspense fallback={<p className="mt-10 text-center text-sm text-slate-400">Connecting Outlook…</p>}>
      <GmailCallback name="Outlook" />
    </Suspense>
  );
}
