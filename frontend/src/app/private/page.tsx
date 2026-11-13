import PrivateNotice from "./PrivateNotice";

// Shown instead of owner-only pages (see proxy.ts)
export default function Page() {
  return <PrivateNotice />;
}
