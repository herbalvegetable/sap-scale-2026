import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  Building2,
  CalendarClock,
  ChevronDown,
  ChevronUp,
  CircleDollarSign,
  Flag,
  Info,
  Landmark,
  RefreshCw,
  Route,
  UserRoundCheck,
} from "lucide-react";
import { api } from "../lib/api";
import type { ActionableInsight } from "../lib/types";
import { humanizeLabel } from "../lib/utils";
import { BusinessFolderAnnex } from "./BusinessFolderAnnex";
import { CaseAssistantWidget } from "./CaseAssistantWidget";
import { ExplanationPanel } from "./ExplanationPanel";
import { RiskBreakdown } from "./RiskBreakdown";
import { RiskScoreGauge } from "./RiskScoreGauge";
import { StatusBadge, TierBadge } from "./AlertTable";
import { TransactionActivityChart } from "./TransactionActivityChart";

const money = (value: number, code: string) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: code, maximumFractionDigits: 0 }).format(value);

export function AlertDetailView({ alertId, onBack }: { alertId: string; onBack: () => void }) {
  const queryClient = useQueryClient();
  const [ownersOpen, setOwnersOpen] = useState(false);
  const [annexOpen, setAnnexOpen] = useState(false);
  const [actionableInsight, setActionableInsight] = useState<ActionableInsight>();
  const [draftOverride, setDraftOverride] = useState<string>();
  useEffect(() => {
    setActionableInsight(undefined);
    setDraftOverride(undefined);
  }, [alertId]);
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
  const generateActions = useMutation({
    mutationFn: () => api.generateInsights(alertId),
    onSuccess: (data) => setActionableInsight(data),
  });
  const decideInsight = useMutation({
    mutationFn: (payload: {
      decision: "approved" | "overridden";
      edited_draft_notes: string;
      reason_code?: string;
      free_text?: string;
    }) =>
      api.decideInsight(alertId, {
        decision: payload.decision,
        edited_draft_notes: payload.edited_draft_notes,
        reason_code: payload.reason_code,
        free_text: payload.free_text,
      }),
    onSuccess: (data) => setActionableInsight(data.insight),
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
  const thresholdBreach = `${data.alert_type} ${data.description}`.toUpperCase().includes("THRESHOLD");
  return (
    <main className="page-shell detail-page">
      <div className="detail-toolbar">
        <button className="back-button" onClick={onBack}><ArrowLeft size={17} /> Back to case queue</button>
        <button className="annex-button" onClick={() => setAnnexOpen(true)}><BookOpen size={16} /> Annex & glossary</button>
      </div>
      {thresholdBreach && (
        <div className="threshold-banner" role="alert">
          <AlertTriangle size={21} />
          <div><strong>{humanizeLabel("THRESHOLD_BREACH")}</strong><span>This transaction crossed a configured monitoring threshold and requires prompt human review.</span></div>
        </div>
      )}
      <header className="detail-hero">
        <div>
          <div className="detail-hero__meta">
            <TierBadge tier={data.score.tier} />
            <span>{data.id}</span>
            <span>·</span>
            <StatusBadge alert={data} />
          </div>
          <h1>{data.company_name}</h1>
          <p>{humanizeLabel(data.alert_type)} — {data.description}</p>
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
            <span>Priority assessed · {new Date(data.score.generated_at).toLocaleString()}</span>
            <button
              className="text-button"
              onClick={() => refreshScore.mutate()}
              disabled={refreshScore.isPending}
            >
              <RefreshCw className={refreshScore.isPending ? "spin" : ""} size={14} /> Refresh score
            </button>
            {data.score.confidence && (
              <div className={`hero-confidence hero-confidence--${data.score.confidence.level}`}>
                <div className="hero-confidence__header">
                  <span className="hero-confidence__pill">
                    Data confidence: {data.score.confidence.level}
                  </span>
                </div>
                <ul>
                  {data.score.confidence.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      </header>

      <section className="context-grid" aria-label="Alert context">
        <article><CircleDollarSign /><span>Transaction</span><strong>{money(data.amount, data.currency)}</strong><small>{data.transaction.channel} · {data.transaction.purpose}</small></article>
        <article><Building2 /><span>Entity profile</span><strong>{data.company.risk_rating} KYC risk</strong><small>{data.company.industry}</small></article>
        <article><UserRoundCheck /><span>Screening</span><strong>{data.company.sanctions_match ? "Sanctions match" : "No sanctions match"}</strong><small>{data.company.pep ? "PEP association present" : "No PEP association"}</small></article>
        <article><Landmark /><span>Prior exposure</span><strong>{data.company.prior_cases} compliance cases</strong><small>{data.company.beneficial_owner_layers} beneficial owners</small></article>
        <article><CalendarClock /><span>Initiated</span><strong>{new Date(data.transaction.occurred_at).toLocaleDateString()}</strong><small>{data.transaction.counterparty}</small></article>
        <article className="baseline-card">
          <Flag />
          <span>Baseline <span className="tooltip" title="The entity's historical average transaction amount, used as the expected-activity reference."><Info size={12} /></span></span>
          <strong>{money(data.company.baseline_average_amount, data.currency)}</strong>
          <small>Historical expected average amount</small>
        </article>
        <article><CircleDollarSign /><span>Amount ratio</span><strong>{data.amount_ratio.toFixed(1)}×</strong><small>Current amount ÷ baseline average</small></article>
      </section>

      <TransactionActivityChart activity={data.activity} currency={data.currency} />

      <section className="panel owners-panel">
        <button className="owners-toggle" onClick={() => setOwnersOpen((current) => !current)} aria-expanded={ownersOpen}>
          <div>
            <p className="eyebrow">Entity ownership</p>
            <h2>Beneficial owners <span>{data.beneficial_owners.length}</span></h2>
          </div>
          <span>{ownersOpen ? "Collapse" : "Expand full ownership details"} {ownersOpen ? <ChevronUp /> : <ChevronDown />}</span>
        </button>
        {ownersOpen && (
          data.beneficial_owners.length ? (
            <div className="owners-list">
              {data.beneficial_owners.map((owner) => (
                <article key={owner.id}>
                  <div className="owner-avatar">{owner.name.split(" ").map((part) => part[0]).join("").slice(0, 2)}</div>
                  <div><strong>{owner.name}</strong><span>{owner.relationship} · {owner.ownership_percentage.toFixed(2)}%</span></div>
                  <div><small>Nationality</small><b>{owner.nationality}</b></div>
                  <div><small>Residence</small><b>{owner.residence}</b></div>
                  <div className="owner-flags">
                    {owner.is_pep && <span>PEP</span>}
                    {owner.sanctions_match && <span className="danger">Sanctions match</span>}
                    {!owner.is_pep && !owner.sanctions_match && <span className="clear">No screening flags</span>}
                  </div>
                </article>
              ))}
            </div>
          ) : <div className="empty-state"><p>No beneficial-owner records were supplied for this entity.</p></div>
        )}
      </section>

      <div className="detail-columns">
        <RiskBreakdown factors={data.score.factors} />
        <ExplanationPanel
          explanation={explanation.data}
          loading={explanation.isLoading}
          refreshing={refreshExplanation.isPending}
          onRefresh={() => refreshExplanation.mutate()}
          actionableInsight={actionableInsight}
          generatingActions={generateActions.isPending}
          actionError={generateActions.error?.message}
          onGenerateActions={() => generateActions.mutate()}
          deciding={decideInsight.isPending}
          decisionError={decideInsight.error?.message}
          draftOverride={draftOverride}
          onApprove={(editedDraftNotes) =>
            decideInsight.mutate({ decision: "approved", edited_draft_notes: editedDraftNotes })
          }
          onOverride={(editedDraftNotes, reasonCode, freeText) =>
            decideInsight.mutate({
              decision: "overridden",
              edited_draft_notes: editedDraftNotes,
              reason_code: reasonCode,
              free_text: freeText,
            })
          }
        />
      </div>
      <BusinessFolderAnnex open={annexOpen} onClose={() => setAnnexOpen(false)} />
      <CaseAssistantWidget
        alertId={alertId}
        hasInsight={Boolean(actionableInsight)}
        onInsertDraft={(snippet) => {
          setDraftOverride(snippet);
          if (actionableInsight) {
            setActionableInsight({ ...actionableInsight, draft_notes: snippet });
          }
        }}
      />
    </main>
  );
}
