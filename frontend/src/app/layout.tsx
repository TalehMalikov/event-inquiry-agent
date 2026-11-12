import type { Metadata, Viewport } from "next";
import { Suspense } from "react";
import { Geist, Geist_Mono } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import CompanyScope from "@/components/CompanyScope";
import Nav from "@/components/Nav";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Event Inquiry Agent",
  description: "AI drafts every reply. You approve what matters.",
  // Installed on an iPhone home screen: full-screen app with our icon (needed for notifications on iOS)
  appleWebApp: { capable: true, title: "Inbox AI", statusBarStyle: "default" },
  icons: { apple: "/apple-touch-icon.png" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0f172a",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-slate-50 text-slate-900">
        {/* Inside <body>, as Clerk requires when Next.js cache components are on */}
        <ClerkProvider taskUrls={{ "choose-organization": "/choose-company" }}>
          {/* Suspense: who's signed in and the URL are only known at request time */}
          <Suspense fallback={<div className="h-14 border-b border-slate-200 bg-white" />}>
            <Nav />
          </Suspense>
          <main className="mx-auto w-full max-w-3xl flex-1 px-4 pb-24 pt-6 sm:pb-10">
            <Suspense fallback={<p className="text-sm text-slate-400">Loading…</p>}>
              <CompanyScope>{children}</CompanyScope>
            </Suspense>
          </main>
        </ClerkProvider>
      </body>
    </html>
  );
}
