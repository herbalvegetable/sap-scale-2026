import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Clock3, Search, ShieldAlert, Sparkles } from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { api } from "../lib/api";
import type { RiskTier } from "../lib/types";
import { AlertTable } from "./AlertTable";
import { Button } from "./ui/button";

interface Props {
  onSelectAlert: (id: string) => void;
}

export function Dashboard({ onSelectAlert }: Props) {
  const [tier, setTier] = useState<RiskTier | "all">("all");
  const [search, setSearch] = useState("");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const stats = useQuery({ queryKey: ["stats"], queryFn: api.stats });
  const alerts = useQuery({
    queryKey: ["alerts", tier, search, sortOrder],
    queryFn: () => api.alerts({ tier, search, sortOrder, pageSize: 50 }),
  });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: 1 });

  const chartData = stats.data
    ? [
        { name: "High", value: stats.data.high, color: "#dc2626" },
        { name: "Medium", value: stats.data.medium, color: "#f59e0b" },
        { name: "Low", value: stats.data.low, color: "#10b981" },
      ]
    : [];

  return (
    <main className="page-shell">
      <header className="page-header">
        <div>
          <p className="eyebrow">Financial crime operations</p>
          <h1>Alert command centre</h1>
          <p>Prioritise the alerts that create the greatest regulatory exposure.</p>
        </div>
        <div className="live-indicator">
          <i />
          {health.data?.data_mode === "hana" ? "Live SAP HANA data" : "Resilient demo data"}
        </div>
      </header>

      {health.data?.status === "degraded" && (
        <div className="notice" role="status">
          <AlertTriangle size={18} />
          <span>
            Degraded mode: {health.data.data_mode === "demo" ? "demo data is active" : "AI fallback scoring is active"}.
            Results show their provenance on the alert detail page.
          </span>
        </div>
      )}

      <section className="metric-grid" aria-label="Alert queue overview">
        <article className="metric-card metric-card--primary">
          <span className="metric-icon"><ShieldAlert /></span>
          <div>
            <p>Total alerts</p>
            <strong>{stats.data?.total ?? "—"}</strong>
            <span>{stats.data?.open_alerts ?? "—"} require review</span>
          </div>
        </article>
        <article className="metric-card">
          <span className="metric-icon metric-icon--danger"><AlertTriangle /></span>
          <div>
            <p>High priority</p>
            <strong>{stats.data?.high ?? "—"}</strong>
            <span>Review first</span>
          </div>
        </article>
        <article className="metric-card">
          <span className="metric-icon metric-icon--neutral"><Sparkles /></span>
          <div>
            <p>Average score</p>
            <strong>{stats.data?.average_score ?? "—"}</strong>
            <span>Across the active queue</span>
          </div>
        </article>
        <article className="metric-card">
          <span className="metric-icon metric-icon--neutral"><Clock3 /></span>
          <div>
            <p>Review target</p>
            <strong>&lt; 24h</strong>
            <span>Down from 1–3 days</span>
          </div>
        </article>
        <article className="metric-card metric-card--chart">
          <div>
            <p>Risk distribution</p>
            <span>Queue composition</span>
          </div>
          <div className="mini-chart">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={chartData} innerRadius={22} outerRadius={34} dataKey="value" paddingAngle={4}>
                  {chartData.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </article>
      </section>

      <section className="panel queue-panel">
        <div className="queue-header">
          <div>
            <p className="eyebrow">Prioritised queue</p>
            <h2>Transaction alerts</h2>
          </div>
          <div className="queue-controls">
            <label className="search-box">
              <Search size={17} aria-hidden="true" />
              <span className="sr-only">Search alerts</span>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search entity, alert or transaction"
              />
            </label>
            <div className="segmented" aria-label="Filter by risk tier">
              {(["all", "high", "medium", "low"] as const).map((item) => (
                <button
                  key={item}
                  className={tier === item ? "active" : ""}
                  onClick={() => setTier(item)}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
        </div>
        {alerts.isLoading ? (
          <div className="loading-state"><span className="spinner" /> Loading prioritised alerts…</div>
        ) : alerts.isError ? (
          <div className="error-state">
            <AlertTriangle />
            <h3>Could not load alerts</h3>
            <p>{alerts.error.message}</p>
            <Button onClick={() => alerts.refetch()}>Try again</Button>
          </div>
        ) : (
          <AlertTable
            alerts={alerts.data?.items ?? []}
            onSelect={onSelectAlert}
            onSort={() => setSortOrder((current) => current === "desc" ? "asc" : "desc")}
          />
        )}
      </section>
    </main>
  );
}
