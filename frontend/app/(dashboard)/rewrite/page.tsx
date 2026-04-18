"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { librariesApi, rewriteApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea, Select } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { PageSpinner } from "@/components/ui/spinner";
import { MODE_LABEL, extractErrorMessage } from "@/lib/utils";
import { Wand2, BookOpen, Info, Languages } from "lucide-react";
import toast from "react-hot-toast";

const MODES = ["conservative", "balanced", "expressive", "precision"] as const;
const CONTRACT_MODES = ["strict", "balanced", "loose"] as const;

const TRANSLATION_LANGS: { value: string; label: string }[] = [
  { value: "uk", label: "Украинский" },
  { value: "pl", label: "Польский" },
  { value: "de", label: "Немецкий" },
  { value: "fr", label: "Французский" },
];

const MODE_DESCRIPTION: Record<string, string> = {
  conservative: "Максимальное сохранение структуры, минимальные изменения",
  balanced: "Оптимальный баланс между изменениями и сохранением смысла",
  expressive: "Максимальная стилистическая трансформация с опорой на образцы",
  precision: "Token-level выбор токенов с минимальным AI-score (требует локальную модель)",
};

export default function RewritePage() {
  const router = useRouter();
  const [text, setText] = useState("");
  const [libraryId, setLibraryId] = useState("");
  const [mode, setMode] = useState<string>("balanced");
  const [contractMode, setContractMode] = useState<string>("balanced");
  const [translationTarget, setTranslationTarget] = useState<string>("");

  const { data: libraries, isLoading: libLoading } = useQuery({
    queryKey: ["libraries"],
    queryFn: librariesApi.list,
  });

  const create = useMutation({
    mutationFn: async () => {
      const task = await rewriteApi.create({
        original_text: text,
        library_id: libraryId,
        rewrite_mode: mode,
        semantic_contract_mode: contractMode,
        input_constraints: translationTarget ? { translation_target: translationTarget } : undefined,
      });
      await rewriteApi.run(task.id);
      return task;
    },
    onSuccess: (task) => {
      toast.success("Задача создана и запущена");
      router.push(`/tasks/${task.id}`);
    },
    onError: (e: unknown) => {
      toast.error(extractErrorMessage(e, "Ошибка создания задачи"));
    },
  });

  if (libLoading) return <PageSpinner />;
  const libList: Library[] = Array.isArray(libraries) ? libraries : [];

  const wordCount = text.trim().split(/\s+/).filter(Boolean).length;
  const selectedLib = libList.find(l => l.id === libraryId);

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Переписать текст</h1>
        <p className="text-sm text-slate-500 mt-1">Создайте задачу переписывания с выбором стиля</p>
      </div>

      <div className="space-y-5">
        {/* Text input */}
        <Card>
          <CardHeader>
            <CardTitle>Исходный текст</CardTitle>
            <CardDescription>Вставьте текст для переписывания</CardDescription>
          </CardHeader>
          <CardContent>
            <Textarea
              value={text}
              onChange={e => setText(e.target.value)}
              placeholder="Вставьте текст здесь..."
              rows={8}
              className="text-sm"
            />
            <p className="text-xs text-slate-400 mt-2 text-right">
              {wordCount} слов{wordCount > 300 ? " · будет разбит на части" : ""}
            </p>
          </CardContent>
        </Card>

        {/* Library */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BookOpen className="h-4 w-4" /> Библиотека стилей
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {libList.length === 0 ? (
              <p className="text-sm text-amber-600">
                Нет библиотек.{" "}
                <Link href="/libraries" className="underline">Создайте первую</Link>
              </p>
            ) : (
              <>
                <Select
                  value={libraryId}
                  onChange={e => setLibraryId(e.target.value)}
                  label="Выберите библиотеку"
                >
                  <option value="">— не выбрана —</option>
                  {libList.map(l => (
                    <option key={l.id} value={l.id}>
                      {l.name} ({l.language.toUpperCase()}, {l.sample_count ?? 0} образцов)
                    </option>
                  ))}
                </Select>
                {selectedLib && (
                  <div className="flex gap-1.5 flex-wrap">
                    <Badge variant="outline">{selectedLib.language.toUpperCase()}</Badge>
                    <Badge variant="outline">{selectedLib.category}</Badge>
                    {selectedLib.quality_tier && (
                      <Badge className="bg-green-100 text-green-800">{selectedLib.quality_tier}</Badge>
                    )}
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>

        {/* Settings */}
        <Card>
          <CardHeader><CardTitle>Параметры</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            {/* Mode selection */}
            <div className="space-y-2">
              <p className="text-sm font-medium text-slate-700">Режим переписывания</p>
              <div className="grid grid-cols-2 gap-2">
                {MODES.map(m => (
                  <button
                    key={m}
                    onClick={() => setMode(m)}
                    className={`rounded-lg border p-3 text-left transition-all ${
                      mode === m
                        ? "border-indigo-500 bg-indigo-50 ring-1 ring-indigo-500"
                        : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                    }`}
                  >
                    <p className="text-sm font-medium text-slate-800">{MODE_LABEL[m]}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{MODE_DESCRIPTION[m]}</p>
                  </button>
                ))}
              </div>
            </div>

            <Select
              label="Семантический контракт"
              value={contractMode}
              onChange={e => setContractMode(e.target.value)}
            >
              {CONTRACT_MODES.map(m => (
                <option key={m} value={m}>
                  {m === "strict" ? "Строгий — все сущности" : m === "balanced" ? "Сбалансированный — сущности + числа" : "Свободный — ключевые термины"}
                </option>
              ))}
            </Select>

            <div className="flex items-start gap-2 rounded-lg bg-blue-50 p-3">
              <Info className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
              <p className="text-xs text-blue-700">
                Тексты длиннее 300 слов автоматически разбиваются на части с контекстным соединением.
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Translation layer */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Languages className="h-4 w-4" /> Перевод с адаптацией
            </CardTitle>
            <CardDescription>
              После переписывания текст будет переведён и адаптирован на выбранный язык
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Select
              value={translationTarget}
              onChange={e => setTranslationTarget(e.target.value)}
              label="Целевой язык (необязательно)"
            >
              <option value="">— не переводить —</option>
              {TRANSLATION_LANGS.map(l => (
                <option key={l.value} value={l.value}>{l.label}</option>
              ))}
            </Select>
          </CardContent>
        </Card>

        {/* Submit */}
        <Button
          className="w-full h-11 text-base"
          disabled={!text.trim() || !libraryId}
          loading={create.isPending}
          onClick={() => create.mutate()}
        >
          <Wand2 className="h-5 w-5" />
          Запустить переписывание
        </Button>
      </div>
    </div>
  );
}

interface Library {
  id: string; name: string; language: string; category: string;
  quality_tier?: string; is_single_voice: boolean; sample_count?: number;
}
