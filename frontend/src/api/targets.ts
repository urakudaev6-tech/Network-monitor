// Все запросы к API — здесь. Компоненты используют эти функции.

import { apiFetch } from "./client";
import type { CheckResult, MonitorResult, Target, TargetCreate } from "../types";

export const api = {
  health: () => apiFetch<{ status: string }>("/health"),

  listTargets: () => apiFetch<Target[]>("/targets"),

  getTarget: (id: number) => apiFetch<Target>(`/targets/${id}`),

  addTarget: (payload: TargetCreate) =>
    apiFetch<Target>("/targets", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  deleteTarget: (id: number) =>
    apiFetch<void>(`/targets/${id}`, { method: "DELETE" }),

  runMonitor: () =>
    apiFetch<MonitorResult[]>("/monitor/run", { method: "POST" }),

  getResults: () => apiFetch<MonitorResult[]>("/monitor/results"),

  getHistory: (id: number, limit = 100) =>
    apiFetch<CheckResult[]>(`/targets/${id}/history?limit=${limit}`),
};