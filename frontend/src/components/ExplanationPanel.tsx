import { CheckCircle2, FileSearch, Info, RefreshCw, ListChecks } from "lucide-react";
import type { ActionableInsight, Explanation } from "../lib/types";
import { RecommendationCard } from "./RecommendationCard";

interface Props {
  explanation?: Explanation;
  loading: boolean;
  refreshing: boolean;
  onRefresh: () => void;
  actionableInsight?: ActionableInsight;
  generatingActions: boolean;
  actionError?: string;
  onGenerateActions: () => void;
  deciding: boolean;
  decisionError?: string;
  draftOverride?: string;
  onApprove: (editedDraftNotes: string) => void;
  onOverride: (editedDraftNotes: string, reasonCode: string, freeText: string) => void;
}

export function ExplanationPanel({
  explanation,
  loading,
  refreshing,
  onRefresh,
  actionableInsight,
  generatingActions,
  actionError,
  onGenerateActions,
  deciding,
  decisionError,
  draftOverride,
  onApprove,
  onOverride,
}: Props) {
  return (
    <section className="panel intelligence-panel" aria-labelledby="intelligence-heading">
      <div className="panel__heading">
        <div>
          <p className="eyebrow">Investigator brief</p>
          <h2 id="intelligence-heading">Risk intelligence</h2>
        </div>
        <button className="icon-button" onClick={onRefresh} disabled={refreshing} aria-label="Regenerate explanation">
          <RefreshCw className={refreshing ? "spin" : ""} size={18} />
        </button>
      </div>
      {loading ? (
        <div className="intelligence-loading">
          <span className="spinner" />
          <div>
            <strong>Assembling grounded context</strong>
            <p>Retrieving transaction, entity, geography and case evidence…</p>
          </div>
        </div>
      ) : explanation ? (
        <>
          <div className="ai-summary">
            <Info size={24} aria-hidden="true" />
            <p>{explanation.summary}</p>
          </div>
          <div className="intelligence-grid">
            <div>
              <h3><FileSearch size={17} /> Key risk drivers</h3>
              <ul>{explanation.key_drivers.map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
            <div>
              <h3><CheckCircle2 size={17} /> Mitigating observations</h3>
              <ul>{explanation.mitigating_factors.map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
          </div>
          <div className="recommended-checks">
            <h3>Recommended investigator checks</h3>
            <ol>{explanation.recommended_checks.map((item) => <li key={item}>{item}</li>)}</ol>
          </div>
          <div className="actionable-insights">
            <button className="ui-button ui-button--primary ui-button--default" onClick={onGenerateActions} disabled={generatingActions}>
              {generatingActions ? <RefreshCw className="spin" size={16} /> : <ListChecks size={16} />}
              {generatingActions ? "Generating recommendation…" : "Generate Actionable Insights"}
            </button>
            <p>Produces a structured recommendation card with urgency, evidence, precedent, and a draft note — never auto-executed.</p>
            {actionError && <div className="inline-error">{actionError}</div>}
            {actionableInsight && (
              <RecommendationCard
                key={actionableInsight.insight_id}
                insight={actionableInsight}
                deciding={deciding}
                decisionError={decisionError}
                draftOverride={draftOverride}
                onApprove={onApprove}
                onOverride={onOverride}
              />
            )}
          </div>
          <div className="model-note">
            <Info size={15} />
            <span>
              Generated {new Date(explanation.generated_at).toLocaleString()}. Human review is required.
            </span>
          </div>
        </>
      ) : (
        <div className="empty-state"><p>No explanation is available.</p></div>
      )}
    </section>
  );
}
