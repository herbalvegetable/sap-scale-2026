import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Clock3,
  Gauge,
  Layers3,
  Scale,
  ShieldAlert,
  TimerReset,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../lib/api";
import { PerformanceAssistantWidget } from "./PerformanceAssistantWidget";
import { Button } from "./ui/button";

const moneyCompact = (value: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);

const pct = (value: number) => `${(value * 100).toFixed(1)}%`;

const monthLabel = (value: string) => {
  const [year, month] = value.split("-");
  const date = new Date(Number(year), Number(month) - 1, 1);
  return date.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
};

export function PerformanceDashboard() {
  const [range, setRange] = useState<6 | 12>(12);
  const operations = useQuery({ queryKey: ["operations"], queryFn: api.operations });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: 1 });

  const months = useMemo(() => {
    const series = operations.data?.months ?? [];
    return series.slice(-range).map((point) => ({
      ...point,
      label: monthLabel(point.month),
    }));
  }, [operations.data?.months, range]);

  const kpis = operations.data?.kpis;

  if (operations.isLoading) {
    return (
      <main className="page-shell">
        <div className="loading-state"><span className="spinner" /> Loading operations analytics…</div>
      </main>
    );
  }

  if (operations.isError || !operations.data || !kpis) {
    return (
      <main className="page-shell">
        <div className="error-state">
          <AlertTriangle />
          <h3>Could not load performance analytics</h3>
          <p>{operations.error?.message ?? "Operations metrics are unavailable."}</p>
          <Button onClick={() => operations.refetch()}>Try again</Button>
        </div>
      </main>
    );
  }

  const reviewHours = kpis.median_review_hours;
  const reviewDays = reviewHours == null ? null : reviewHours / 24;
  const backlogImproving = kpis.backlog_change < 0;

  return (
    <main className="page-shell performance-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Operations impact</p>
          <h1>Performance dashboard</h1>
          <p>
            Track backlog, review speed, and SLA exposure against TrustSphere’s stated pain points:
            slow manual reviews, rising cost pressure, and unresolved regulatory risk.
            Backlog KPIs cover the full ops population; the scored work queue is the prioritised subset for triage.
          </p>
        </div>
        <div className="performance-header-controls">
          <div className="live-indicator">
            <i />
            {operations.data.data_mode === "hana" ? "Live SAP HANA aggregates" : "Demo operations series"}
          </div>
          <div className="segmented" aria-label="Select history range">
            <button className={range === 6 ? "active" : ""} onClick={() => setRange(6)}>6M</button>
            <button className={range === 12 ? "active" : ""} onClick={() => setRange(12)}>12M</button>
          </div>
        </div>
      </header>

      {health.data?.data_mode === "demo" && (
        <div className="notice" role="status">
          <AlertTriangle size={18} />
          <span>
            Demo mode: this page shows an illustrative 12-month trend, not live bank performance.
            Live HANA mode aggregates the full alert population for monthly series.
          </span>
        </div>
      )}

      <section className="performance-kpi-grid" aria-label="Operations KPIs">
        <article className="metric-card metric-card--primary">
          <span className="metric-icon"><Layers3 /></span>
          <div>
            <p>Current backlog</p>
            <strong>{kpis.backlog}</strong>
            <span>{kpis.open_alerts} open · {kpis.investigating} investigating</span>
          </div>
        </article>
        <article className="metric-card">
          <span className="metric-icon metric-icon--neutral"><Clock3 /></span>
          <div>
            <p>Median review time</p>
            <strong>
              {reviewDays == null ? "—" : reviewDays < 1 ? `${reviewHours?.toFixed(1)}h` : `${reviewDays.toFixed(1)}d`}
            </strong>
            <span>Baseline 1–3 days · target &lt; 24h</span>
          </div>
        </article>
        <article className="metric-card">
          <span className="metric-icon metric-icon--neutral"><Gauge /></span>
          <div>
            <p>Closure rate</p>
            <strong>{pct(kpis.closure_rate)}</strong>
            <span>{kpis.period_closed.toLocaleString()} closed / {kpis.period_raised.toLocaleString()} raised</span>
          </div>
        </article>
        <article className="metric-card">
          <span className="metric-icon metric-icon--neutral"><Scale /></span>
          <div>
            <p>SLA adherence</p>
            <strong>{pct(kpis.sla_adherence_rate)}</strong>
            <span>Cases without SLA breach in period</span>
          </div>
        </article>
        <article className="metric-card">
          <span className="metric-icon metric-icon--neutral"><TimerReset /></span>
          <div>
            <p>Review-timeout rate</p>
            <strong>{pct(kpis.review_timeout_rate)}</strong>
            <span>Closed due to expired review timeline</span>
          </div>
        </article>
        <article className="metric-card">
          <span className="metric-icon metric-icon--danger"><ShieldAlert /></span>
          <div>
            <p>High-priority unresolved</p>
            <strong>{kpis.high_priority_unresolved}</strong>
            <span>
              {moneyCompact(kpis.high_priority_exposure_usd)} · scored queue ({kpis.scored_queue_size})
            </span>
          </div>
        </article>
        <article className="metric-card">
          <span className={`metric-icon ${backlogImproving ? "metric-icon--neutral" : "metric-icon--danger"}`}>
            {backlogImproving ? <TrendingDown /> : <TrendingUp />}
          </span>
          <div>
            <p>Backlog change (latest month)</p>
            <strong>{kpis.backlog_change > 0 ? `+${kpis.backlog_change}` : kpis.backlog_change}</strong>
            <span>Raised minus closed · unresolved exposure {moneyCompact(kpis.unresolved_exposure_usd)}</span>
          </div>
        </article>
      </section>

      <section className="performance-chart-grid">
        <article className="panel performance-chart-card">
          <div className="panel__heading">
            <div>
              <p className="eyebrow">Throughput</p>
              <h2>Cases closed by month</h2>
            </div>
          </div>
          <div className="performance-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={months} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="closed" name="Closed" fill="#2563eb" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </article>

        <article className="panel performance-chart-card">
          <div className="panel__heading">
            <div>
              <p className="eyebrow">Exposure under review</p>
              <h2>Alerted transaction value by month</h2>
            </div>
          </div>
          <div className="performance-chart">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={months} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(value) => moneyCompact(Number(value))} />
                <Tooltip formatter={(value) => moneyCompact(Number(value))} />
                <Area
                  type="monotone"
                  dataKey="transaction_value_usd"
                  name="Alerted value (USD)"
                  stroke="#0ea5e9"
                  fill="#bae6fd"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </article>

        <article className="panel performance-chart-card">
          <div className="panel__heading">
            <div>
              <p className="eyebrow">Backlog pressure</p>
              <h2>Raised vs closed by month</h2>
            </div>
          </div>
          <div className="performance-chart">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={months} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Legend />
                <Bar dataKey="raised" name="Raised" fill="#93c5fd" radius={[4, 4, 0, 0]} />
                <Line type="monotone" dataKey="closed" name="Closed" stroke="#1d4ed8" strokeWidth={2.5} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </article>

        <article className="panel performance-chart-card">
          <div className="panel__heading">
            <div>
              <p className="eyebrow">Regulatory exposure</p>
              <h2>SLA breaches by month</h2>
            </div>
          </div>
          <div className="performance-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={months} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="sla_breaches" name="SLA breaches" fill="#f59e0b" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </article>
      </section>

      <section className="panel performance-impact">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">Business impact</p>
            <h2>How these metrics map to client pain points</h2>
          </div>
        </div>
        <div className="performance-impact__body">
          <p>
            TrustSphere’s Board asked for demonstrable improvement in financial-crime effectiveness and
            efficiency within 12–18 months. Faster median review time and a falling backlog change reduce
            payment-delay pressure, while improving SLA adherence and fewer review-timeout closures reduce
            unresolved regulatory exposure. These operational levers support the COO’s 30% cost-per-case
            ambition without inventing an unsupported dollar saving in this prototype.
          </p>
          <ul>
            {(operations.data.notes.length ? operations.data.notes : [
              "Metrics use precise operational definitions and distinguish dataset outcomes from client baselines.",
            ]).map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      </section>

      <PerformanceAssistantWidget rangeMonths={range} />
    </main>
  );
}
