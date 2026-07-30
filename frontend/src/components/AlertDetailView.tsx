import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Building2,
  CalendarClock,
  CircleDollarSign,
  Flag,
  Landmark,
  RefreshCw,
  Route,
  UserRoundCheck,
} from "lucide-react";
import { api } from "../lib/api";
import { ExplanationPanel } from "./ExplanationPanel";
import { RiskBreakdown } from "./RiskBreakdown";
import { RiskScoreGauge } from "./RiskScoreGauge";
import { TierBadge } from "./AlertTable";

const money = (value: number, code: string) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: code, maximumFractionDigits: 0 }).format(value);

export function AlertDetailView({ alertId, onBack }: { alertId: string; onBack: () => void }) {
  const queryClient = useQueryClient();
  const alert = useQuery({ queryKey: ["alert", alertId], queryFn: () => api.alert(alertId) });
  const explanation = useQuery({
    queryKey: ["explanation", alertId],
    queryFn: () => api.explanation(alertId),
    enabled: alert.isSuccess,
  });
  const refreshScore = useMutation({
    mutationFn: () => api.refreshScore(alertId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alert", alertId] }),
  });
  const refreshExplanation = useMutation({
    mutationFn: () => api.refreshExplanation(alertId),
    onSuccess: (data) => queryClient.setQueryData(["explanation", alertId], data),
  });

  if (alert.isLoading) {
    return <main className="detail-loading"><span className="spinner" /> Loading alert evidence…</main>;
  }
  if (alert.isError || !alert.data) {
    return (
      <main className="detail-loading">
        <h2>Alert unavailable</h2>
        <p>{alert.error?.message ?? "The requested alert could not be found."}</p>
        <button className="button button--primary" onClick={onBack}>Return to queue</button>
      </main>
    );
  }

  const data = alert.data;
  return (
    <main className="page-shell detail-page">
      <button className="back-button" onClick={onBack}><ArrowLeft size={17} /> Back to alert queue</button>
      <header className="detail-hero">
        <div>
          <div className="detail-hero__meta">
            <TierBadge tier={data.score.tier} />
            <span>{data.id}</span>
            <span>·</span>
            <span>{data.status}</span>
          </div>
          <h1>{data.company_name}</h1>
          <p>{data.alert_type} — {data.description}</p>
          <div className="detail-hero__route">
            <Route size={17} />
            {data.origin_country} <span>→</span> {data.destination_country}
            <b>{money(data.amount, data.currency)}</b>
          </div>
        </div>
        <div className="hero-score">
          <RiskScoreGauge score={data.score.total} tier={data.score.tier} />
          <div>
            <strong>{data.score.tier.toUpperCase()} PRIORITY</strong>
            <span>{data.score.provenance === "ai" ? "AI-assessed" : "Resilient fallback"} · {data.score.model}</span>
            <button
              className="text-button"
              onClick={() => refreshScore.mutate()}
              disabled={refreshScore.isPending}
            >
              <RefreshCw className={refreshScore.isPending ? "spin" : ""} size={14} /> Refresh score
            </button>
          </div>
        </div>
      </header>

      <section className="context-grid" aria-label="Alert context">
        <article><CircleDollarSign /><span>Transaction</span><strong>{money(data.amount, data.currency)}</strong><small>{data.transaction.channel} · {data.transaction.purpose}</small></article>
        <article><Building2 /><span>Entity profile</span><strong>{data.company.risk_rating} KYC risk</strong><small>{data.company.industry}</small></article>
        <article><UserRoundCheck /><span>Screening</span><strong>{data.company.sanctions_match ? "Sanctions match" : "No sanctions match"}</strong><small>{data.company.pep ? "PEP association present" : "No PEP association"}</small></article>
        <article><Landmark /><span>Prior exposure</span><strong>{data.company.prior_cases} compliance cases</strong><small>{data.company.beneficial_owner_layers} beneficial owners</small></article>
        <article><CalendarClock /><span>Initiated</span><strong>{new Date(data.transaction.occurred_at).toLocaleDateString()}</strong><small>{data.transaction.counterparty}</small></article>
        <article><Flag /><span>Baseline</span><strong>{money(data.company.baseline_average_amount, data.currency)}</strong><small>Average transaction amount</small></article>
      </section>

      <div className="detail-columns">
        <RiskBreakdown factors={data.score.factors} />
        <ExplanationPanel
          explanation={explanation.data}
          loading={explanation.isLoading}
          refreshing={refreshExplanation.isPending}
          onRefresh={() => refreshExplanation.mutate()}
        />
      </div>
    </main>
  );
}
