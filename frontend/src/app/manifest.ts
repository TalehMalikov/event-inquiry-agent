import type { MetadataRoute } from "next";

// Makes the site installable ("Add to Home Screen"), which phones need for notifications.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Event Inquiry Agent",
    short_name: "Inbox AI",
    description: "AI drafts every reply. You approve what matters.",
    start_url: "/",
    display: "standalone",
    background_color: "#c5382f", // launch screen behind the icon
    theme_color: "#0f172a",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
