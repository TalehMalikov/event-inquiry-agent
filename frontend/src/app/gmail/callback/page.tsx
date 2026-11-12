import { Suspense } from "react";
import GmailCallback from "./GmailCallback";

// Google sends the owner back here after "Connect Gmail".
export default function Page() {
  return (
    <Suspense fallback={<p className="mt-10 text-center text-sm text-slate-400">Connecting Gmail…</p>}>
      <GmailCallback />
    </Suspense>
  );
}
