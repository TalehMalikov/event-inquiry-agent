import type { Metadata } from "next";
import Architecture from "./Architecture";

export const metadata: Metadata = {
  title: "Architecture · Event Inquiry Agent",
  description: "Interactive map of how Event Inquiry Agent is built: frontend, backend, AI agent, RAG, database, Gmail, Outlook.",
};

// Public page (see proxy.ts): no company data here, only how the system fits together.
export default function Page() {
  return <Architecture />;
}
