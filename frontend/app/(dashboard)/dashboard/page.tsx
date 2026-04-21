"use client";

import { useQuery } from "@tanstack/react-query";
import { librariesApi, rewriteApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PageSpinner } from "@/components/ui/spinner";
import { BookOpen, PenLine, CheckSquare, TrendingUp } from "lucide-react";
import Link from "next/link";
import { formatDate, STATUS_COLOR, MODE_LABEL } from "@/lib/utils";

export default function DashboardPage() {
  const { data: libraries, isLoading: libLoading } = useQuery({
    queryKey: ["libraries"],
    queryFn: librariesApi.list,
  });

  const { data: tasks, isLoading: taskLoading } = useQuery({
    queryKey: ["tasks"],
    queryFn: rewriteApi.list,
  });

  if (libLoading || taskLoading) return <PageSpinner />;

  const libList = Array.isArray(libraries) ? libraries : [];
  const taskList = Array.isArray(tasks) ? tasks : [];

  const stats = [
    { label: "Библиотеки", value: libList.length, icon: BookOpen, href: "/libraries", color: "text-indigo-600" },
    { label: "Задач переписывания", value: taskList.length, icon: PenLine, href: "/tasks", color: "text-emerald-600" },
    { label: "Завершено", value: taskList.filter((t: { status: string }) => t.status === "completed").length, icon: CheckSquare, href: "/tasks", color: "text-blue-600" },
    { label: "Образцов", value: libList.reduce((a: number, l: { sample_count?: number }) => a + (l.sample_count || 0), 0), icon: TrendingUp, href: "/libraries", color: "text-amber-600" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Дашборд</h1>
        <p className="text-sm text-slate-500 mt-1">Обзор проекта</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map((s) => (
          <Link key={s.label} href={s.href}>
            <Card className="hover:shadow-md transition-shadow cursor-pointer">
              <CardContent className="flex items-center gap-4 p-5">
                <div className={`rounded-lg bg-slate-50 p-2.5 ${s.color}`}>
                  <s.icon className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-slate-900">{s.value}</p>
                  <p className="text-xs text-slate-500">{s.label}</p>
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Recent libraries */}
        <Card>
          <CardHeader>
            <CardTitle>Последние библиотеки</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {libList.length === 0 && (
              <p className="text-sm text-slate-400 py-4 text-center">
                Нет библиотек.{" "}
                <Link href="/libraries" className="text-indigo-600 hover:underline">Создать первую</Link>
              </p>
            )}
            {libList.slice(0, 5).map((lib: { id: string; name: string; language: string; quality_tier: string | null; sample_count?: number }) => (
              <Link key={lib.id} href={`/libraries/${lib.id}`}>
                <div className="flex items-center justify-between rounded-lg p-2.5 hover:bg-slate-50 transition-colors">
                  <div className="flex items-center gap-2.5">
                    <BookOpen className="h-4 w-4 text-slate-400" />
                    <div>
                      <p className="text-sm font-medium text-slate-800">{lib.name}</p>
                      <p className="text-xs text-slate-400">{lib.language.toUpperCase()} · {lib.sample_count ?? 0} образцов</p>
                    </div>
                  </div>
                  {lib.quality_tier && (
                    <Badge className="bg-green-100 text-green-800">{lib.quality_tier}</Badge>
                  )}
                </div>
              </Link>
            ))}
            {libList.length > 5 && (
              <Link href="/libraries" className="block text-center text-xs text-indigo-500 hover:underline pt-1">
                Все {libList.length} библиотек →
              </Link>
            )}
          </CardContent>
        </Card>

        {/* Recent tasks */}
        <Card>
          <CardHeader>
            <CardTitle>Последние задачи</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {taskList.length === 0 && (
              <p className="text-sm text-slate-400 py-4 text-center">
                Нет задач.{" "}
                <Link href="/rewrite" className="text-indigo-600 hover:underline">Создать первую</Link>
              </p>
            )}
            {taskList.slice(0, 5).map((task: { id: string; status: string; rewrite_mode: string; created_at: string; original_text: string }) => (
              <Link key={task.id} href={`/tasks/${task.id}`}>
                <div className="flex items-center justify-between rounded-lg p-2.5 hover:bg-slate-50 transition-colors">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-800 truncate">{task.original_text.slice(0, 60)}…</p>
                    <p className="text-xs text-slate-400">{MODE_LABEL[task.rewrite_mode] ?? task.rewrite_mode} · {formatDate(task.created_at)}</p>
                  </div>
                  <Badge className={STATUS_COLOR[task.status]}>{task.status}</Badge>
                </div>
              </Link>
            ))}
            {taskList.length > 5 && (
              <Link href="/tasks" className="block text-center text-xs text-indigo-500 hover:underline pt-1">
                Все {taskList.length} задач →
              </Link>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
