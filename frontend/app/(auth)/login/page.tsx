"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import toast from "react-hot-toast";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

export default function LoginPage() {
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [isRegister, setIsRegister] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setLoading(true);
    try {
      let data;
      if (isRegister) {
        data = await authApi.register(email, name || email.split("@")[0]);
        toast.success("Аккаунт создан!");
      } else {
        data = await authApi.token(email);
      }
      setAuth(data.access_token, data.user_id);
      router.push("/dashboard");
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Ошибка входа";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <div className="mb-2 flex items-center gap-2">
          <span className="text-2xl font-bold text-indigo-600">Humanizator</span>
          <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-xs font-semibold text-indigo-700">3</span>
        </div>
        <CardTitle>{isRegister ? "Регистрация" : "Вход"}</CardTitle>
        <CardDescription>
          {isRegister ? "Создайте аккаунт для доступа к системе" : "Войдите в вашу учётную запись"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {isRegister && (
            <Input
              label="Имя"
              placeholder="Иван Иванов"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          )}
          <Input
            label="Email"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <Button type="submit" loading={loading} className="w-full">
            {isRegister ? "Создать аккаунт" : "Войти"}
          </Button>
          <button
            type="button"
            onClick={() => setIsRegister(!isRegister)}
            className="text-center text-sm text-slate-500 hover:text-indigo-600 transition-colors"
          >
            {isRegister ? "Уже есть аккаунт? Войти" : "Нет аккаунта? Зарегистрироваться"}
          </button>
        </form>
      </CardContent>
    </Card>
  );
}
