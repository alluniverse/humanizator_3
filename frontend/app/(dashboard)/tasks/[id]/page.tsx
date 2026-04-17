"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { rewriteApi, evaluationApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PageSpinner, Spinner } from "@/components/ui/spinner";
import { STATUS_COLOR, MODE_LABEL, formatDate, extractErrorMessage } from "@/lib/utils";
import { ArrowLeft, Play, ChevronDown, ChevronUp, Shield, BarChart2, CheckSquare2 } from "lucide-react";
import Link from "next/link";
import toast from "react-hot-toast";

export default function TaskDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const [expandedVariant, setExpandedVariant] = useState<string | null>(null);
  const [evalTarget, setEvalTarget] = useState<string | null>(null);

  const { data: task, isLoading } = useQuery({
    queryKey: ["task", id],
    queryFn: () => rewriteApi.get(id),
    refetchInterval: (query) => {
      const status = (query.state.data as TaskDetail | undefined)?.status;
      return status === "pending" || status === "running" ? 3000 : false;
    },
  });

  const { data: variants, isLoading: variantsLoading } = useQuery({
    queryKey: ["task-variants", id],
    queryFn: () => rewriteApi.variants(id),
    enabled: !!task && task.status === "completed",
  });

  const runTask = useMutation({
    mutationFn: () => rewriteApi.run(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["task", id] });
      toast.success("Задача запущена");
    },
    onError: (e: unknown) => {
      toast.error(extractErrorMessage(e, "Ошибка запуска"));
    },
  });

  const evalMetrics = useMutation({
    mutationFn: (text: string) => evaluationApi.absoluteMetrics(id, text),
    onSuccess: (data, text) => {
      setEvalTarget(text);
      qc.setQueryData(["eval-metrics", text], data);
    },
    onError: () => toast.error("Ошибка оценки метрик"),
  });

  const evalAdversarial = useMutation({
    mutationFn: (text: string) => evaluationApi.adversarialRobustness(id, text),
    onSuccess: (data, text) => {
      qc.setQueryData(["eval-adversarial", text], data);
    },
    onError: () => toast.error("Ошибка adversarial проверки"),
  });

  if (isLoading) return <PageSpinner />;
  if (!task) return <div className="text-slate-500 p-6">Задача не найдена</div>;

  const variantList: Variant[] = Array.isArray(variants) ? variants : [];

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-start gap-4">
        <button onClick={() => router.back()} className="mt-1 text-slate-400 hover:text-slate-700">
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-2xl font-bold text-slate-900">Задача</h1>
            <Badge className={STATUS_COLOR[task.status]}>{task.status}</Badge>
            <Badge variant="outline">{MODE_LABEL[task.rewrite_mode] ?? task.rewrite_mode}</Badge>
          </div>
          <p className="text-xs text-slate-400 mt-1">Создана {formatDate(task.created_at)}</p>
        </div>
        <div className="flex gap-2">
          {task.status === "completed" && variantList.length > 0 && (
            <Link href={`/hitl/${id}`}>
              <Button variant="outline" size="sm">
                <CheckSquare2 className="h-4 w-4" /> Проверить HITL
              </Button>
            </Link>
          )}
          {(task.status === "pending" || task.status === "failed") && (
            <Button size="sm" onClick={() => runTask.mutate()} loading={runTask.isPending}>
              <Play className="h-4 w-4" />
              {task.status === "failed" ? "Перезапустить" : "Запустить"}
            </Button>
          )}
        </div>
      </div>

      {/* Original text */}
      <Card>
        <CardHeader><CardTitle>Исходный текст</CardTitle></CardHeader>
        <CardContent>
          <p className="text-sm text-slate-700 whitespace-pre-wrap">{task.original_text}</p>
        </CardContent>
      </Card>

      {/* Status info */}
      {task.status === "running" && (
        <div className="flex items-center gap-3 rounded-lg bg-blue-50 border border-blue-200 p-4">
          <Spinner className="h-5 w-5 text-blue-500" />
          <p className="text-sm text-blue-700">Задача выполняется... Страница обновится автоматически.</p>
        </div>
      )}

      {task.status === "failed" && task.error_message && (
        <div className="rounded-lg bg-red-50 border border-red-200 p-4">
          <p className="text-sm font-medium text-red-700">Ошибка выполнения</p>
          <p className="text-xs text-red-600 mt-1 font-mono">{task.error_message}</p>
        </div>
      )}

      {/* Variants */}
      {task.status === "completed" && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-slate-800">
            Варианты переписывания {variantsLoading ? "" : `(${variantList.length})`}
          </h2>

          {variantsLoading ? (
            <PageSpinner />
          ) : variantList.length === 0 ? (
            <div className="py-10 text-center text-slate-400">Нет вариантов</div>
          ) : (
            variantList.map((v) => {
              const isExpanded = expandedVariant === v.id;
              const metricsData = qc.getQueryData<EvalMetrics>(["eval-metrics", v.rewritten_text]);
              const adversarialData = qc.getQueryData<AdversarialResult>(["eval-adversarial", v.rewritten_text]);

              return (
                <Card key={v.id} className="overflow-hidden">
                  <CardContent className="p-0">
                    {/* Variant header */}
                    <div
                      className="flex items-center gap-3 p-4 cursor-pointer hover:bg-slate-50"
                      onClick={() => setExpandedVariant(isExpanded ? null : v.id)}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
                            Вариант #{v.variant_index ?? 1}
                          </span>
                          {v.review_status && (
                            <Badge variant="outline" className="text-xs">
                              {v.review_status}
                            </Badge>
                          )}
                          {v.scores && (
                            <div className="flex gap-2 ml-2">
                              {v.scores.semantic_similarity != null && (
                                <span className="text-xs text-slate-500">
                                  Sim: <strong>{(v.scores.semantic_similarity * 100).toFixed(0)}%</strong>
                                </span>
                              )}
                              {v.scores.ai_score != null && (
                                <span className="text-xs text-slate-500">
                                  AI: <strong>{(v.scores.ai_score * 100).toFixed(0)}%</strong>
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                        <p className="text-sm text-slate-700 line-clamp-2">{v.rewritten_text}</p>
                      </div>
                      {isExpanded ? (
                        <ChevronUp className="h-4 w-4 text-slate-400 flex-shrink-0" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-slate-400 flex-shrink-0" />
                      )}
                    </div>

                    {/* Expanded content */}
                    {isExpanded && (
                      <div className="border-t border-slate-100 p-4 space-y-4 bg-slate-50/50">
                        <p className="text-sm text-slate-700 whitespace-pre-wrap">{v.rewritten_text}</p>

                        {/* Evaluation actions */}
                        <div className="flex gap-2 flex-wrap">
                          <Button
                            size="sm"
                            variant="outline"
                            loading={evalMetrics.isPending && evalTarget === v.rewritten_text}
                            onClick={() => evalMetrics.mutate(v.rewritten_text)}
                          >
                            <BarChart2 className="h-4 w-4" /> Метрики
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            loading={evalAdversarial.isPending}
                            onClick={() => evalAdversarial.mutate(v.rewritten_text)}
                          >
                            <Shield className="h-4 w-4" /> Adversarial
                          </Button>
                        </div>

                        {/* Metrics result */}
                        {metricsData && (
                          <div className="rounded-lg border bg-white p-3 space-y-2">
                            <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Метрики</p>
                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                              {Object.entries(metricsData).map(([key, val]) =>
                                typeof val === "number" ? (
                                  <div key={key} className="text-center">
                                    <p className="text-lg font-bold text-slate-800">{(val * 100).toFixed(1)}<span className="text-xs">%</span></p>
                                    <p className="text-xs text-slate-500">{key.replace(/_/g, " ")}</p>
                                  </div>
                                ) : null
                              )}
                            </div>
                          </div>
                        )}

                        {/* Adversarial result */}
                        {adversarialData && (
                          <div className="rounded-lg border bg-white p-3 space-y-2">
                            <div className="flex items-center gap-2">
                              <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Adversarial тест</p>
                              <Badge className={adversarialData.passed ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}>
                                {adversarialData.passed ? "Пройден" : "Провален"}
                              </Badge>
                            </div>
                            <p className="text-xs text-slate-500">
                              Средняя схожесть: <strong>{(adversarialData.mean_similarity * 100).toFixed(1)}%</strong>
                            </p>
                            {adversarialData.fragile_attacks?.length > 0 && (
                              <div className="flex gap-1 flex-wrap">
                                {adversarialData.fragile_attacks.map((a: string) => (
                                  <Badge key={a} variant="outline" className="text-xs text-red-600 border-red-200">{a}</Badge>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

interface TaskDetail {
  id: string;
  status: string;
  rewrite_mode: string;
  original_text: string;
  created_at: string;
  error_message?: string;
}

interface Variant {
  id: string;
  rewritten_text: string;
  variant_index?: number;
  review_status?: string;
  scores?: { semantic_similarity?: number; ai_score?: number; fluency?: number };
}

interface EvalMetrics {
  [key: string]: number | string;
}

interface AdversarialResult {
  passed: boolean;
  mean_similarity: number;
  fragile_attacks: string[];
}
