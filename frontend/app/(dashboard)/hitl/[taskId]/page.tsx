"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { hitlApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/input";
import { PageSpinner } from "@/components/ui/spinner";
import { formatDate } from "@/lib/utils";
import { ArrowLeft, CheckCircle2, XCircle, MessageSquare, AlertCircle } from "lucide-react";
import toast from "react-hot-toast";

const REVIEW_ACTIONS = [
  { key: "approve", label: "Принять", icon: CheckCircle2, color: "text-green-600", bg: "bg-green-50 border-green-200 hover:bg-green-100" },
  { key: "reject", label: "Отклонить", icon: XCircle, color: "text-red-600", bg: "bg-red-50 border-red-200 hover:bg-red-100" },
  { key: "request_revision", label: "Доработать", icon: MessageSquare, color: "text-amber-600", bg: "bg-amber-50 border-amber-200 hover:bg-amber-100" },
] as const;

export default function HitlReviewPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const router = useRouter();
  const [selectedVariant, setSelectedVariant] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [reviewedIds, setReviewedIds] = useState<Set<string>>(new Set());

  const { data: bundle, isLoading } = useQuery({
    queryKey: ["hitl-bundle", taskId],
    queryFn: () => hitlApi.bundle(taskId, false),
  });

  const review = useMutation({
    mutationFn: ({ variantId, action }: { variantId: string; action: string }) =>
      hitlApi.review(taskId, variantId, action, comment.trim() || undefined),
    onSuccess: (_, { variantId, action }) => {
      setReviewedIds(prev => new Set([...prev, variantId]));
      setComment("");
      setSelectedVariant(null);
      toast.success(
        action === "approve" ? "Вариант принят" :
        action === "reject" ? "Вариант отклонён" :
        "Отправлено на доработку"
      );
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Ошибка отправки";
      toast.error(msg);
    },
  });

  if (isLoading) return <PageSpinner />;
  if (!bundle) return <div className="text-slate-500 p-6">Данные недоступны</div>;

  const variants: HitlVariant[] = Array.isArray(bundle.variants) ? bundle.variants : [];
  const task = bundle.task;

  return (
    <div className="max-w-4xl space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <button onClick={() => router.back()} className="mt-1 text-slate-400 hover:text-slate-700">
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-slate-900">HITL Проверка</h1>
          <p className="text-sm text-slate-500 mt-1">
            Задача {taskId.slice(0, 8)}… · {formatDate(task?.created_at)}
          </p>
        </div>
        {reviewedIds.size > 0 && (
          <Badge className="bg-green-100 text-green-800">{reviewedIds.size} проверено</Badge>
        )}
      </div>

      {/* Original text */}
      <Card>
        <CardHeader><CardTitle>Исходный текст</CardTitle></CardHeader>
        <CardContent>
          <p className="text-sm text-slate-700 whitespace-pre-wrap">{task?.original_text}</p>
        </CardContent>
      </Card>

      {/* Hallucination warning */}
      {bundle.hallucination_results?.some((h: HallucinationResult) => h.has_hallucinations) && (
        <div className="flex items-start gap-3 rounded-lg bg-red-50 border border-red-200 p-4">
          <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-red-700">Обнаружены потенциальные галлюцинации</p>
            <p className="text-xs text-red-600 mt-0.5">Проверьте варианты внимательно перед принятием.</p>
          </div>
        </div>
      )}

      {/* Variants */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-slate-800">Варианты ({variants.length})</h2>

        {variants.length === 0 ? (
          <div className="py-10 text-center text-slate-400">Нет вариантов для проверки</div>
        ) : (
          variants.map((v, idx) => {
            const isReviewed = reviewedIds.has(v.id);
            const isSelected = selectedVariant === v.id;
            const hallucination = bundle.hallucination_results?.find(
              (h: HallucinationResult) => h.variant_id === v.id
            );

            return (
              <Card
                key={v.id}
                className={`transition-all ${isReviewed ? "opacity-60" : ""} ${isSelected ? "ring-2 ring-indigo-500" : ""}`}
              >
                <CardContent className="p-5 space-y-4">
                  {/* Variant header */}
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
                      Вариант #{idx + 1}
                    </span>
                    {v.review_status && (
                      <Badge variant="outline" className="text-xs">{v.review_status}</Badge>
                    )}
                    {isReviewed && (
                      <Badge className="bg-green-100 text-green-800 text-xs">Проверено</Badge>
                    )}
                    {hallucination?.has_hallucinations && (
                      <Badge className="bg-red-100 text-red-700 text-xs">
                        <AlertCircle className="h-3 w-3 mr-1" /> Галлюцинации
                      </Badge>
                    )}
                  </div>

                  {/* Text */}
                  <p className="text-sm text-slate-700 whitespace-pre-wrap">{v.rewritten_text}</p>

                  {/* Scores */}
                  {v.scores && (
                    <div className="flex gap-4 flex-wrap">
                      {v.scores.semantic_similarity != null && (
                        <div className="text-center">
                          <p className="text-base font-bold text-slate-800">
                            {(v.scores.semantic_similarity * 100).toFixed(0)}%
                          </p>
                          <p className="text-xs text-slate-500">Схожесть</p>
                        </div>
                      )}
                      {v.scores.ai_score != null && (
                        <div className="text-center">
                          <p className="text-base font-bold text-slate-800">
                            {(v.scores.ai_score * 100).toFixed(0)}%
                          </p>
                          <p className="text-xs text-slate-500">AI-score</p>
                        </div>
                      )}
                      {v.scores.fluency != null && (
                        <div className="text-center">
                          <p className="text-base font-bold text-slate-800">
                            {(v.scores.fluency * 100).toFixed(0)}%
                          </p>
                          <p className="text-xs text-slate-500">Fluency</p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Review section */}
                  {!isReviewed && (
                    <div className="space-y-3 pt-2 border-t border-slate-100">
                      {isSelected && (
                        <Textarea
                          label="Комментарий (необязательно)"
                          value={comment}
                          onChange={e => setComment(e.target.value)}
                          rows={2}
                          placeholder="Добавьте комментарий к решению..."
                        />
                      )}
                      <div className="flex gap-2 flex-wrap">
                        {REVIEW_ACTIONS.map(action => {
                          const Icon = action.icon;
                          return (
                            <button
                              key={action.key}
                              onClick={() => {
                                if (!isSelected) {
                                  setSelectedVariant(v.id);
                                } else {
                                  review.mutate({ variantId: v.id, action: action.key });
                                }
                              }}
                              disabled={review.isPending}
                              className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium transition-all ${action.bg} ${action.color}`}
                            >
                              <Icon className="h-4 w-4" />
                              {action.label}
                            </button>
                          );
                        })}
                        {isSelected && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => { setSelectedVariant(null); setComment(""); }}
                          >
                            Отмена
                          </Button>
                        )}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })
        )}
      </div>

      {/* Done button */}
      {reviewedIds.size === variants.length && variants.length > 0 && (
        <div className="flex justify-center pt-4">
          <div className="text-center space-y-3">
            <div className="flex items-center gap-2 text-green-600">
              <CheckCircle2 className="h-5 w-5" />
              <p className="font-medium">Все варианты проверены</p>
            </div>
            <Button onClick={() => router.push(`/tasks/${taskId}`)}>
              Вернуться к задаче
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

interface HitlVariant {
  id: string;
  rewritten_text: string;
  review_status?: string;
  scores?: { semantic_similarity?: number; ai_score?: number; fluency?: number };
}

interface HallucinationResult {
  variant_id: string;
  has_hallucinations: boolean;
}
