"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Briefcase } from "lucide-react";
import { cn } from "@/lib/cn";

export function Header() {
  const pathname = usePathname();
  const navItems = [
    { href: "/dashboard", label: "Dashboard" },
    { href: "/saved", label: "Saved Jobs" },
  ];

  return (
    <header className="sticky top-0 z-30 border-b border-zinc-200 bg-white/80 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold text-zinc-900">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand text-white">
            <Briefcase className="h-4 w-4" />
          </span>
          <span>Opportunity.ai</span>
        </Link>

        <nav className="flex items-center gap-1">
          {navItems.map((item) => {
            const active = pathname === item.href || pathname?.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  active
                    ? "bg-brand-soft text-brand"
                    : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900",
                )}
              >
                {item.label}
              </Link>
            );
          })}
          <button
            type="button"
            className="ml-2 rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:border-zinc-400 hover:bg-zinc-50"
          >
            Sign in
          </button>
        </nav>
      </div>
    </header>
  );
}
