"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/api";

const LINKS = [
  { href: "/", label: "Inbox", icon: "📥" },
  { href: "/venue", label: "Venue", icon: "🏠" },
  { href: "/settings", label: "Settings", icon: "⚙️" },
];

function Logo() {
  return (
    <span className="flex items-center gap-2 font-semibold tracking-tight">
      <span className="flex gap-0.5" aria-hidden>
        <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
        <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
        <span className="h-2.5 w-2.5 rounded-full bg-rose-500" />
      </span>
      Event Inquiry Agent
    </span>
  );
}

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  async function logout() {
    await api.logout().catch(() => {});
    router.push("/login");
  }

  if (pathname === "/login") {
    return (
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-14 max-w-3xl items-center px-4">
          <Logo />
        </div>
      </header>
    );
  }

  return (
    <>
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-3xl items-center justify-between px-4">
          <Link href="/">
            <Logo />
          </Link>
          <div className="flex items-center gap-1">
            <nav className="hidden gap-1 sm:flex">
              {LINKS.map((l) => (
                <Link
                  key={l.href}
                  href={l.href}
                  className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                    isActive(l.href) ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  {l.label}
                </Link>
              ))}
            </nav>
            <button onClick={logout} className="rounded-lg px-3 py-1.5 text-sm text-slate-500 hover:bg-slate-100">
              Log out
            </button>
          </div>
        </div>
      </header>

      {/* Bottom tab bar on phones */}
      <nav className="fixed inset-x-0 bottom-0 z-20 flex border-t border-slate-200 bg-white sm:hidden">
        {LINKS.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className={`flex flex-1 flex-col items-center gap-0.5 py-2 text-xs font-medium ${
              isActive(l.href) ? "text-slate-900" : "text-slate-400"
            }`}
          >
            <span className="text-lg" aria-hidden>
              {l.icon}
            </span>
            {l.label}
          </Link>
        ))}
      </nav>
    </>
  );
}
