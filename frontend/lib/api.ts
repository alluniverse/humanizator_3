import axios from "axios";

export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
});

// Attach JWT on every request
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("access_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Auto-logout on 401
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

// ── Auth ─────────────────────────────────────────────────────────────
export const authApi = {
  register: (email: string, full_name: string) =>
    api.post("/auth/register", { email, full_name }).then((r) => r.data),
  token: (email: string) =>
    api.post(`/auth/token?email=${encodeURIComponent(email)}`).then((r) => r.data),
};

// ── Libraries ────────────────────────────────────────────────────────
export const librariesApi = {
  list: () => api.get("/libraries").then((r) => r.data),
  get: (id: string) => api.get(`/libraries/${id}`).then((r) => r.data),
  create: (data: Record<string, unknown>) =>
    api.post("/libraries", data).then((r) => r.data),
  update: (id: string, data: Record<string, unknown>) =>
    api.patch(`/libraries/${id}`, data).then((r) => r.data),
  delete: (id: string) => api.delete(`/libraries/${id}`).then((r) => r.data),

  samples: (id: string) =>
    api.get(`/libraries/${id}/samples`).then((r) => r.data),
  addSample: (id: string, data: Record<string, unknown>) =>
    api.post(`/libraries/${id}/samples`, data).then((r) => r.data),
  deleteSample: (libId: string, sampleId: string) =>
    api.delete(`/libraries/${libId}/samples/${sampleId}`).then((r) => r.data),
  bulkAdd: (id: string, samples: unknown[]) =>
    api.post(`/libraries/${id}/samples/bulk`, { samples }).then((r) => r.data),

  diagnostics: (id: string) =>
    api.get(`/libraries/${id}/diagnostics`).then((r) => r.data),
  conflictDetection: (id: string) =>
    api.post(`/libraries/${id}/conflict-detection`).then((r) => r.data),
  voiceInfo: (id: string) =>
    api.get(`/libraries/${id}/voice-info`).then((r) => r.data),
  fluencyWinRate: (id: string) =>
    api.get(`/libraries/${id}/fluency-win-rate`).then((r) => r.data),

  snapshots: (id: string) =>
    api.get(`/libraries/${id}/snapshots`).then((r) => r.data),
  createSnapshot: (id: string, label?: string) =>
    api.post(`/libraries/${id}/snapshots`, null, { params: { label } }).then((r) => r.data),
  restoreSnapshot: (id: string, snapshotId: string) =>
    api.post(`/libraries/${id}/snapshots/${snapshotId}/restore`).then((r) => r.data),

  exportLib: (id: string) =>
    api.get(`/libraries/${id}/export`).then((r) => r.data),

  updateSample: (libId: string, sampleId: string, data: Record<string, unknown>) =>
    api.patch(`/libraries/${libId}/samples/${sampleId}`, data).then((r) => r.data),

  addFromUrl: (id: string, url: string, splitParagraphs = true) =>
    api
      .post(`/libraries/${id}/samples/from-url`, { url, split_paragraphs: splitParagraphs })
      .then((r) => r.data),
};

// ── Rewrite ───────────────────────────────────────────────────────────
export const rewriteApi = {
  create: (data: Record<string, unknown>) =>
    api.post("/rewrite", data).then((r) => r.data),
  get: (id: string) => api.get(`/rewrite/${id}`).then((r) => r.data),
  list: () => api.get("/rewrite").then((r) => r.data),
  run: (id: string) => api.post(`/rewrite/${id}/run`).then((r) => r.data),
  variants: (id: string) =>
    api.get(`/rewrite/${id}/variants`).then((r) => r.data),
  semanticContract: (id: string) =>
    api.get(`/rewrite/${id}/semantic-contract`).then((r) => r.data),
};

// ── HITL ──────────────────────────────────────────────────────────────
export const hitlApi = {
  bundle: (taskId: string, runHallucinationCheck = false) =>
    api.get(`/hitl/${taskId}`, { params: { run_hallucination_check: runHallucinationCheck } }).then((r) => r.data),
  review: (taskId: string, variantId: string, action: string, comment?: string) =>
    api.post(`/hitl/${taskId}/review`, { variant_id: variantId, action, comment }).then((r) => r.data),
};

// ── Evaluation ────────────────────────────────────────────────────────
export const evaluationApi = {
  absoluteMetrics: (taskId: string, variantText: string) =>
    api.post(`/evaluation/${taskId}/absolute-metrics`, null, { params: { variant_text: variantText } }).then((r) => r.data),
  hallucinationCheck: (taskId: string, rewrittenText: string) =>
    api.post(`/evaluation/${taskId}/hallucination-check`, null, { params: { rewritten_text: rewrittenText } }).then((r) => r.data),
  adversarialRobustness: (taskId: string, variantText: string) =>
    api.post(`/evaluation/${taskId}/adversarial-robustness`, null, { params: { variant_text: variantText } }).then((r) => r.data),
};
