"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { librariesApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Textarea } from "@/components/ui/input";
import { PageSpinner, Spinner } from "@/components/ui/spinner";
import { TIER_COLOR, formatDate, truncate } from "@/lib/utils";
import { ArrowLeft, Plus, Trash2, Camera, BarChart2, Download, AlertCircle, CheckCircle2, X, Link2 } from "lucide-react";
import Link from "next/link";
import toast from "react-hot-toast";

export default function LibraryDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const [showAddSample, setShowAddSample] = useState(false);
  const [showAddUrl, setShowAddUrl] = useState(false);
  const [urlForm, setUrlForm] = useState({ url: "", splitParagraphs: true });
  const [sampleForm, setSampleForm] = useState({ content: "", author: "", title: "" });
  const [activeTab, setActiveTab] = useState<"samples" | "analytics" | "snapshots">("samples");

  const { data: library, isLoading } = useQuery({
    queryKey: ["library", id],
    queryFn: () => librariesApi.get(id),
  });

  const { data: samples, isLoading: samplesLoading } = useQuery({
    queryKey: ["library-samples", id],
    queryFn: () => librariesApi.samples(id),
  });

  const { data: diagnostics } = useQuery({
    queryKey: ["library-diagnostics", id],
    queryFn: () => librariesApi.diagnostics(id),
    enabled: activeTab === "analytics",
  });

  const { data: snapshots } = useQuery({
    queryKey: ["library-snapshots", id],
    queryFn: () => librariesApi.snapshots(id),
    enabled: activeTab === "snapshots",
  });

  const addSample = useMutation({
    mutationFn: () => librariesApi.addSample(id, sampleForm),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["library-samples", id] });
      qc.invalidateQueries({ queryKey: ["library", id] });
      setShowAddSample(false);
      setSampleForm({ content: "", author: "", title: "" });
      toast.success("Образец добавлен");
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Ошибка добавления";
      toast.error(msg);
    },
  });

  const addFromUrl = useMutation({
    mutationFn: () => librariesApi.addFromUrl(id, urlForm.url, urlForm.splitParagraphs),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["library-samples", id] });
      qc.invalidateQueries({ queryKey: ["library", id] });
      setShowAddUrl(false);
      setUrlForm({ url: "", splitParagraphs: true });
      toast.success(`Добавлено ${data.added} образцов из «${data.title}»`);
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Ошибка парсинга";
      toast.error(msg);
    },
  });

  const deleteSample = useMutation({
    mutationFn: (sampleId: string) => librariesApi.deleteSample(id, sampleId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["library-samples", id] });
      toast.success("Образец удалён");
    },
  });

  const createSnapshot = useMutation({
    mutationFn: () => librariesApi.createSnapshot(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["library-snapshots", id] });
      toast.success("Снапшот создан");
    },
  });

  const restoreSnapshot = useMutation({
    mutationFn: (snapId: string) => librariesApi.restoreSnapshot(id, snapId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["library-samples", id] });
      qc.invalidateQueries({ queryKey: ["library", id] });
      toast.success("Библиотека восстановлена из снапшота");
    },
  });

  async function handleExport() {
    try {
      const data = await librariesApi.exportLib(id);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `library-${library?.name ?? id}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Экспорт выполнен");
    } catch {
      toast.error("Ошибка экспорта");
    }
  }

  if (isLoading) return <PageSpinner />;
  if (!library) return <div className="text-slate-500 p-6">Библиотека не найдена</div>;

  const sampleList: Sample[] = Array.isArray(samples) ? samples : [];

  const TABS = [
    { key: "samples", label: `Образцы (${sampleList.length})` },
    { key: "analytics", label: "Аналитика" },
    { key: "snapshots", label: "Снапшоты" },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <button onClick={() => router.back()} className="mt-1 text-slate-400 hover:text-slate-700">
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-2xl font-bold text-slate-900">{library.name}</h1>
            <Badge variant="outline">{library.language.toUpperCase()}</Badge>
            <Badge variant="outline">{library.category}</Badge>
            {library.quality_tier && <Badge className={TIER_COLOR[library.quality_tier]}>{library.quality_tier}</Badge>}
            {library.is_single_voice && <Badge className="bg-purple-100 text-purple-800">Single-voice</Badge>}
          </div>
          {library.description && <p className="text-sm text-slate-500 mt-1">{library.description}</p>}
          <p className="text-xs text-slate-400 mt-1">v{library.version} · Создана {formatDate(library.created_at)}</p>
        </div>
        <div className="flex gap-2 flex-shrink-0">
          <Button variant="outline" size="sm" onClick={handleExport}>
            <Download className="h-4 w-4" /> Экспорт
          </Button>
          <Button variant="outline" size="sm" onClick={() => createSnapshot.mutate()} loading={createSnapshot.isPending}>
            <Camera className="h-4 w-4" /> Снапшот
          </Button>
          <Link href="/rewrite">
            <Button size="sm"><Plus className="h-4 w-4" /> Переписать</Button>
          </Link>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200">
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key as typeof activeTab)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === t.key ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-500 hover:text-slate-700"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* SAMPLES TAB */}
      {activeTab === "samples" && (
        <div className="space-y-4">
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => { setShowAddUrl(true); setShowAddSample(false); }}>
              <Link2 className="h-4 w-4" /> По ссылке
            </Button>
            <Button size="sm" onClick={() => { setShowAddSample(true); setShowAddUrl(false); }}>
              <Plus className="h-4 w-4" /> Добавить образец
            </Button>
          </div>

          {showAddUrl && (
            <Card className="border-blue-200 bg-blue-50/30">
              <CardContent className="p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="font-medium text-slate-800 flex items-center gap-2">
                    <Link2 className="h-4 w-4 text-blue-500" /> Добавить из статьи
                  </h4>
                  <button onClick={() => setShowAddUrl(false)}><X className="h-4 w-4 text-slate-400" /></button>
                </div>
                <Input
                  label="Ссылка на статью"
                  value={urlForm.url}
                  onChange={e => setUrlForm(f => ({ ...f, url: e.target.value }))}
                  placeholder="https://www.bbc.com/news/articles/..."
                />
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="split"
                    checked={urlForm.splitParagraphs}
                    onChange={e => setUrlForm(f => ({ ...f, splitParagraphs: e.target.checked }))}
                    className="h-4 w-4 rounded border-slate-300 accent-indigo-600"
                  />
                  <label htmlFor="split" className="text-sm text-slate-600">
                    Разбить на отдельные образцы (по абзацам)
                  </label>
                </div>
                <p className="text-xs text-slate-400">Поддерживаются: BBC, Guardian и большинство новостных сайтов</p>
                <div className="flex gap-2 justify-end">
                  <Button variant="outline" size="sm" onClick={() => setShowAddUrl(false)}>Отмена</Button>
                  <Button
                    size="sm"
                    loading={addFromUrl.isPending}
                    disabled={!urlForm.url.trim()}
                    onClick={() => addFromUrl.mutate()}
                  >
                    Парсить и добавить
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {showAddSample && (
            <Card className="border-indigo-200 bg-indigo-50/30">
              <CardContent className="p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="font-medium text-slate-800">Новый образец</h4>
                  <button onClick={() => setShowAddSample(false)}><X className="h-4 w-4 text-slate-400" /></button>
                </div>
                <Textarea label="Текст" rows={4} value={sampleForm.content}
                  onChange={e => setSampleForm(f => ({...f, content: e.target.value}))}
                  placeholder="Вставьте текст образца..." />
                <div className="grid grid-cols-2 gap-3">
                  <Input label="Автор" value={sampleForm.author}
                    onChange={e => setSampleForm(f => ({...f, author: e.target.value}))} placeholder="Иван Иванов" />
                  <Input label="Заголовок" value={sampleForm.title}
                    onChange={e => setSampleForm(f => ({...f, title: e.target.value}))} placeholder="Необязательно" />
                </div>
                <div className="flex gap-2 justify-end">
                  <Button variant="outline" size="sm" onClick={() => setShowAddSample(false)}>Отмена</Button>
                  <Button size="sm" loading={addSample.isPending} disabled={!sampleForm.content.trim()}
                    onClick={() => addSample.mutate()}>Добавить</Button>
                </div>
              </CardContent>
            </Card>
          )}

          {samplesLoading ? <PageSpinner /> : sampleList.length === 0 ? (
            <div className="py-16 text-center text-slate-400">Нет образцов. Добавьте первый.</div>
          ) : (
            <div className="space-y-2">
              {sampleList.map((s) => (
                <Card key={s.id}>
                  <CardContent className="p-4 flex items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        {s.quality_tier && <Badge className={`${TIER_COLOR[s.quality_tier]} text-xs`}>{s.quality_tier}</Badge>}
                        {s.author && <span className="text-xs text-slate-500">{s.author}</span>}
                        {s.title && <span className="text-xs text-slate-400">· {s.title}</span>}
                      </div>
                      <p className="text-sm text-slate-700 whitespace-pre-wrap">{truncate(s.content, 200)}</p>
                    </div>
                    <button
                      onClick={() => deleteSample.mutate(s.id)}
                      className="text-slate-300 hover:text-red-500 transition-colors flex-shrink-0 mt-1"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ANALYTICS TAB */}
      {activeTab === "analytics" && (
        <div className="space-y-4">
          {!diagnostics ? <PageSpinner /> : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <Card>
                <CardHeader><CardTitle>Качество корпуса</CardTitle></CardHeader>
                <CardContent className="space-y-3">
                  {(["L1", "L2", "L3"] as const).map(tier => (
                    <div key={tier} className="flex items-center gap-3">
                      <Badge className={`w-10 justify-center ${TIER_COLOR[tier]}`}>{tier}</Badge>
                      <div className="flex-1 bg-slate-100 rounded-full h-2">
                        <div
                          className={`h-2 rounded-full ${tier === "L1" ? "bg-green-500" : tier === "L2" ? "bg-yellow-400" : "bg-red-400"}`}
                          style={{ width: `${((diagnostics.tier_distribution?.[tier] ?? 0) / (diagnostics.total_samples || 1)) * 100}%` }}
                        />
                      </div>
                      <span className="text-sm text-slate-600 w-8 text-right">{diagnostics.tier_distribution?.[tier] ?? 0}</span>
                    </div>
                  ))}
                  <p className="text-xs text-slate-500 pt-1">Доминирующий тир: <strong>{diagnostics.dominant_tier}</strong></p>
                  {diagnostics.recommendation && (
                    <div className="flex gap-2 p-2 bg-amber-50 rounded-md text-xs text-amber-800">
                      <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                      {diagnostics.recommendation}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle>Стилевые конфликты</CardTitle>
                    <BarChart2 className="h-4 w-4 text-slate-400" />
                  </div>
                </CardHeader>
                <CardContent>
                  <StyleConflicts libraryId={id} />
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      )}

      {/* SNAPSHOTS TAB */}
      {activeTab === "snapshots" && (
        <div className="space-y-3">
          {!snapshots ? <PageSpinner /> : (snapshots as Snapshot[]).length === 0 ? (
            <div className="py-12 text-center text-slate-400">
              <p>Нет снапшотов.</p>
              <p className="text-sm mt-1">Нажмите «Снапшот» чтобы сохранить текущее состояние.</p>
            </div>
          ) : (
            (snapshots as Snapshot[]).map(snap => (
              <Card key={snap.snapshot_id}>
                <CardContent className="p-4 flex items-center justify-between gap-4">
                  <div>
                    <p className="font-medium text-slate-800">{snap.label}</p>
                    <p className="text-xs text-slate-500">{snap.sample_count} образцов · {formatDate(snap.created_at)}</p>
                  </div>
                  <Button
                    variant="outline" size="sm"
                    onClick={() => { if (confirm("Восстановить библиотеку из снапшота?")) restoreSnapshot.mutate(snap.snapshot_id); }}
                    loading={restoreSnapshot.isPending}
                  >
                    Восстановить
                  </Button>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function StyleConflicts({ libraryId }: { libraryId: string }) {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["library-conflicts", libraryId],
    queryFn: () => librariesApi.conflictDetection(libraryId),
    enabled: false,
  });

  if (isLoading || isFetching) return <div className="flex justify-center py-4"><Spinner /></div>;

  if (!data) return (
    <div className="py-2">
      <Button variant="outline" size="sm" onClick={() => refetch()}>Проверить конфликты</Button>
    </div>
  );

  return (
    <div className="space-y-2">
      <div className={`flex items-center gap-2 text-sm font-medium ${data.has_conflicts ? "text-red-600" : "text-green-600"}`}>
        {data.has_conflicts ? <AlertCircle className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
        {data.has_conflicts ? `${data.conflict_count} конфликт(ов) обнаружено` : "Конфликтов нет"}
      </div>
      {data.recommendations?.map((r: string, i: number) => (
        <p key={i} className="text-xs text-slate-500">• {r}</p>
      ))}
      <Button variant="ghost" size="sm" onClick={() => refetch()}>Обновить</Button>
    </div>
  );
}

interface Sample { id: string; content: string; author?: string; title?: string; quality_tier?: string; }
interface Snapshot { snapshot_id: string; label: string; sample_count: number; created_at: string; library_version: number; }
