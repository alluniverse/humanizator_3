"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { librariesApi } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Select, Textarea } from "@/components/ui/input";
import { PageSpinner } from "@/components/ui/spinner";
import { TIER_COLOR, formatDate } from "@/lib/utils";
import { Plus, BookOpen, Settings, X } from "lucide-react";
import Link from "next/link";
import toast from "react-hot-toast";

const CATEGORIES = ["news", "cinema", "marketing", "science", "social", "art", "entertainment", "personal", "other"];
const LANGUAGES = ["ru", "en", "uk"];

export default function LibrariesPage() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: "", language: "ru", category: "news", description: "", is_single_voice: false });

  const { data: libraries, isLoading } = useQuery({ queryKey: ["libraries"], queryFn: librariesApi.list });

  const create = useMutation({
    mutationFn: () => librariesApi.create(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["libraries"] });
      setShowCreate(false);
      setForm({ name: "", language: "ru", category: "news", description: "", is_single_voice: false });
      toast.success("Библиотека создана");
    },
    onError: () => toast.error("Ошибка создания"),
  });

  if (isLoading) return <PageSpinner />;
  const list: Library[] = Array.isArray(libraries) ? libraries : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Библиотеки стилей</h1>
          <p className="text-sm text-slate-500 mt-1">Коллекции образцов для обучения стилю</p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4" /> Новая библиотека
        </Button>
      </div>

      {/* Create form */}
      {showCreate && (
        <Card className="border-indigo-200 bg-indigo-50/30">
          <CardContent className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-slate-800">Новая библиотека</h3>
              <button onClick={() => setShowCreate(false)}><X className="h-4 w-4 text-slate-400" /></button>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Input label="Название" value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))} placeholder="Мой стиль" />
              <Select label="Язык" value={form.language} onChange={e => setForm(f => ({...f, language: e.target.value}))}>
                {LANGUAGES.map(l => <option key={l} value={l}>{l.toUpperCase()}</option>)}
              </Select>
              <Select label="Категория" value={form.category} onChange={e => setForm(f => ({...f, category: e.target.value}))}>
                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
              </Select>
              <div className="flex items-center gap-2 pt-5">
                <input type="checkbox" id="sv" checked={form.is_single_voice}
                  onChange={e => setForm(f => ({...f, is_single_voice: e.target.checked}))}
                  className="h-4 w-4 rounded border-slate-300 accent-indigo-600" />
                <label htmlFor="sv" className="text-sm font-medium text-slate-700">Single-voice</label>
              </div>
            </div>
            <Textarea label="Описание (необязательно)" value={form.description}
              onChange={e => setForm(f => ({...f, description: e.target.value}))} rows={2} />
            <div className="flex gap-2 justify-end">
              <Button variant="outline" onClick={() => setShowCreate(false)}>Отмена</Button>
              <Button onClick={() => create.mutate()} loading={create.isPending} disabled={!form.name.trim()}>
                Создать
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Library grid */}
      {list.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-slate-400">
          <BookOpen className="h-12 w-12 mb-3 opacity-30" />
          <p className="text-lg font-medium">Нет библиотек</p>
          <p className="text-sm mt-1">Создайте первую библиотеку стилей</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {list.map((lib) => (
            <Card key={lib.id} className="hover:shadow-md transition-shadow">
              <CardContent className="p-5 space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <Link href={`/libraries/${lib.id}`} className="font-semibold text-slate-900 hover:text-indigo-600 transition-colors">
                      {lib.name}
                    </Link>
                    {lib.description && <p className="text-xs text-slate-500 mt-0.5 truncate">{lib.description}</p>}
                  </div>
                  <Link href={`/libraries/${lib.id}`}>
                    <Settings className="h-4 w-4 text-slate-400 hover:text-indigo-600 flex-shrink-0 mt-0.5" />
                  </Link>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  <Badge variant="outline">{lib.language.toUpperCase()}</Badge>
                  <Badge variant="outline">{lib.category}</Badge>
                  {lib.quality_tier && <Badge className={TIER_COLOR[lib.quality_tier]}>{lib.quality_tier}</Badge>}
                  {lib.is_single_voice && <Badge className="bg-purple-100 text-purple-800">Single-voice</Badge>}
                </div>

                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>{lib.sample_count ?? 0} образцов · v{lib.version}</span>
                  <span>{formatDate(lib.created_at)}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

interface Library {
  id: string; name: string; description?: string; language: string; category: string;
  quality_tier?: string; is_single_voice: boolean; sample_count?: number;
  version: number; created_at: string;
}
