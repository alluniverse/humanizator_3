"use client";

import { useQuery } from "@tanstack/react-query";
import { rewriteApi } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageSpinner } from "@/components/ui/spinner";
import { STATUS_COLOR, MODE_LABEL, formatDate } from "@/lib/utils";
import Link from "next/link";
import { Plus, ChevronRight, CheckSquare } from "lucide-react";

export default function TasksPage() {
  const { data: tasks, isLoading } = useQuery({
    queryKey: ["tasks"],
    queryFn: rewriteApi.list,
  });

  if (isLoading) return <PageSpinner />;
  const list: Task[] = Array.isArray(tasks) ? tasks : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Задачи переписывания</h1>
          <p className="text-sm text-slate-500 mt-1">{list.length} задач всего</p>
        </div>
        <Link href="/rewrite">
          <Button><Plus className="h-4 w-4" /> Новая задача</Button>
        </Link>
      </div>

      {list.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-slate-400">
          <CheckSquare className="h-12 w-12 mb-3 opacity-30" />
          <p className="text-lg font-medium">Нет задач</p>
          <p className="text-sm mt-1 mb-4">Создайте первую задачу переписывания</p>
          <Link href="/rewrite"><Button>Переписать текст</Button></Link>
        </div>
      ) : (
        <div className="space-y-2">
          {list.map((task) => (
            <Link key={task.id} href={`/tasks/${task.id}`}>
              <Card className="hover:shadow-md transition-shadow cursor-pointer">
                <CardContent className="p-4 flex items-center gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate">
                      {task.original_text.slice(0, 100)}…
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <Badge variant="outline" className="text-xs">{MODE_LABEL[task.rewrite_mode] ?? task.rewrite_mode}</Badge>
                      <span className="text-xs text-slate-400">{formatDate(task.created_at)}</span>
                    </div>
                  </div>
                  <Badge className={STATUS_COLOR[task.status]}>{task.status}</Badge>
                  <ChevronRight className="h-4 w-4 text-slate-300 flex-shrink-0" />
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

interface Task {
  id: string; status: string; rewrite_mode: string; original_text: string; created_at: string;
}
