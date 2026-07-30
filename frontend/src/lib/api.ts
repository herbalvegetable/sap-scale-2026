import type {
  ActionableInsight,
  AlertDetail,
  AlertPage,
  AlertStats,
  ChatResponse,
  ChatThreadResponse,
  Explanation,
  InsightDecisionRequest,
  InsightDecisionResponse,
  RiskTier,
  ServiceHealth,
} from "./types";

const API_BASE = import.meta.env.VITE_API_URL ?? "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      message = payload.detail ?? message;
    } catch {
      // Keep the status-based error when the body is not JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export interface AlertQuery {
  page?: number;
  pageSize?: number;
  tier?: RiskTier | "all";
  status?: string;
  search?: string;
  sortBy?: "score" | "created_at" | "amount" | "company_name";
  sortOrder?: "asc" | "desc";
}

export const api = {
  health: () => request<ServiceHealth>("/health"),
  stats: () => request<AlertStats>("/alerts/stats"),
  alerts: (query: AlertQuery = {}) => {
    const params = new URLSearchParams({
      page: String(query.page ?? 1),
      page_size: String(query.pageSize ?? 20),
      sort_by: query.sortBy ?? "score",
      sort_order: query.sortOrder ?? "desc",
    });
    if (query.tier && query.tier !== "all") params.set("tier", query.tier);
    if (query.status) params.set("status", query.status);
    if (query.search) params.set("search", query.search);
    return request<AlertPage>(`/alerts?${params}`);
  },
  alert: (id: string) => request<AlertDetail>(`/alerts/${id}`),
  explanation: (id: string) => request<Explanation>(`/alerts/${id}/explanation`),
  refreshScore: (id: string) =>
    request<AlertDetail["score"]>(`/alerts/${id}/score`, { method: "POST" }),
  refreshExplanation: (id: string) =>
    request<Explanation>(`/alerts/${id}/explain`, { method: "POST" }),
  generateInsights: (id: string) =>
    request<ActionableInsight>(`/alerts/${id}/insights`, { method: "POST" }),
  getInsights: (id: string) => request<ActionableInsight>(`/alerts/${id}/insights`),
  decideInsight: (id: string, body: InsightDecisionRequest) =>
    request<InsightDecisionResponse>(`/alerts/${id}/insights/decision`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  chatHistory: (id: string) => request<ChatThreadResponse>(`/alerts/${id}/chat`),
  chat: (id: string, message: string) =>
    request<ChatResponse>(`/alerts/${id}/chat`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
};
