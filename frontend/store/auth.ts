import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  token: string | null;
  userId: string | null;
  setAuth: (token: string, userId: string) => void;
  logout: () => void;
  isAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      userId: null,
      setAuth: (token, userId) => {
        localStorage.setItem("access_token", token);
        set({ token, userId });
      },
      logout: () => {
        localStorage.removeItem("access_token");
        set({ token: null, userId: null });
      },
      isAuthenticated: () => !!get().token,
    }),
    { name: "humanizator-auth" }
  )
);
