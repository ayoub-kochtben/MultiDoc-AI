"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, FileStack, MessageSquare, Settings, Sparkles } from "lucide-react";

const NAV = [
  { href: "/", label: "Chat", icon: MessageSquare },
  { href: "/documents", label: "Documents", icon: FileStack },
  { href: "/dashboard", label: "Tableau de bord", icon: BarChart3 },
  { href: "/settings", label: "Paramètres", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex w-16 shrink-0 flex-col border-r border-slate-200 bg-white md:w-60 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex h-14 items-center gap-2 border-b border-slate-200 px-4 dark:border-slate-800">
        <div className="grid size-8 place-items-center rounded-lg bg-accent-600 text-white">
          <Sparkles size={18} />
        </div>
        <div className="hidden md:block">
          <div className="text-sm font-semibold leading-tight">MultiDoc AI</div>
          <div className="text-[11px] text-slate-500">RAG 100 % local</div>
        </div>
      </div>
      <nav className="flex-1 space-y-1 p-2">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              title={label}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                active
                  ? "bg-accent-50 text-accent-700 dark:bg-accent-500/15 dark:text-accent-100"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
            >
              <Icon size={18} className="shrink-0" />
              <span className="hidden md:inline">{label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
