"use client";

import { useAuth } from "@clerk/nextjs";

// Re-mounts the page whenever the user switches company, so no data from the previous company stays on screen.
export default function CompanyScope({ children }: { children: React.ReactNode }) {
  const { orgId } = useAuth();
  return <div key={orgId ?? "none"}>{children}</div>;
}
