"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BookOpen, PenLine, CheckSquare, LayoutDashboard, LogOut, ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";

const NAV = [
  { href: "/dashboard", label: "Дашборд", icon: LayoutDashboard },
  { href: "/libraries", label: "Библиотеки", icon: BookOpen },
  { href: "/rewrite", label: "Переписать текст", icon: PenLine },
  { href: "/tasks", label: "Задачи", icon: CheckSquare },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const logout = useAuthStore((s) => s.logout);

  function handleLogout() {
    logout();
    router.push("/login");
  }

  return (
    <aside className="flex h-screen w-60 flex-col border-r border-slate-200 bg-white">
      {/* Logo */}
      <div className="flex h-14 items-center gap-2 border-b border-slate-200 px-5">
        <span className="text-xl font-bold text-indigo-600">Humanizator</span>
        <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-xs font-semibold text-indigo-700">3</span>
      </div>

      {/* Nav */}
      <nav className="flex flex-1 flex-col gap-0.5 p-3 overflow-y-auto">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-indigo-50 text-indigo-700"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              )}
            >
              <Icon className="h-4 w-4 flex-shrink-0" />
              {label}
              {active && <ChevronRight className="ml-auto h-3.5 w-3.5 text-indigo-400" />}
            </Link>
          );
        })}
      </nav>

      {/* Logout */}
      <div className="border-t border-slate-200 p-3">
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-slate-500 hover:bg-red-50 hover:text-red-600 transition-colors"
        >
          <LogOut className="h-4 w-4" />
          Выйти
        </button>
      </div>
    </aside>
  );
}
