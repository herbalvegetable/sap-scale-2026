import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  GitBranch,
  History,
  Route,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import type { ActionableInsight, RecommendedAction } from "../lib/types";

const ACTION_LABELS: Record<RecommendedAction, string> = {
  clear: "Clear",
  escalate_tier2: "Escalate to Tier 2",
  request_kyc: "Request Additional KYC/Info",
  draft_sar: "Draft SAR",
};

const OVERRIDE_REASONS = [
  { value: "additional_context", label: "Additional context available" },
  { value: "evidence_insufficient", label: "Evidence insufficient" },
  { value: "policy_exception", label: "Policy exception" },
  { value: "other", label: "Other" },
];

interface Props {
  insight: ActionableInsight;
  deciding: boolean;
  decisionError?: string;
  draftOverride?: string;
  onApprove: (editedDraftNotes: string) => void;
  onOverride: (editedDraftNotes: string, reasonCode: string, freeText: string) => void;
}

export function RecommendationCard({
  insight,
  deciding,
  decisionError,
  draftOverride,
  onApprove,
  onOverride,
}: Props) {
  const [draftNotes, setDraftNotes] = useState(insight.draft_notes);
  const [showOverride, setShowOverride] = useState(false);
  const [reasonCode, setReasonCode] = useState(OVERRIDE_REASONS[0].value);
  const [freeText, setFreeText] = useState("");
  const decided = insight.status === "approved" || insight.status === "overridden" || insight.status === "actioned";

  useEffect(() => {
    if (draftOverride != null) setDraftNotes(draftOverride);
  }, [draftOverride]);

  return (
    <div className="recommendation-card" aria-label="Actionable insight recommendation">
      <div className="recommendation-card__header">
        <div>
          <p className="eyebrow">Workflow recommendation</p>
          <h3>Structured next step</h3>
        </div>
        <span className={`action-badge action-badge--${insight.recommended_action}`}>
          {ACTION_LABELS[insight.recommended_action]}
        </span>
      </div>

      {insight.confidence === "low" && (
        <div className="confidence-banner" role="status">
          <AlertTriangle size={16} />
          <div>
            <strong>Low confidence</strong>
            <span>{insight.confidence_reason}</span>
          </div>
        </div>
      )}

      <p className="recommendation-rationale">{insight.rationale}</p>

      <div className="recommendation-metrics">
        <div className="urgency-meter" aria-label={`Urgency exposure score ${insight.urgency_score}`}>
          <div className="urgency-meter__label">
            <ShieldAlert size={15} />
            <span>Urgency / exposure</span>
            <strong>{insight.urgency_score.toFixed(0)}</strong>
          </div>
          <div className="urgency-meter__track">
            <div className="urgency-meter__fill" style={{ width: `${Math.min(100, insight.urgency_score)}%` }} />
          </div>
          <small>Distinct from the risk score — estimates exposure growth while unresolved.</small>
        </div>
        <div className={`confidence-pill confidence-pill--${insight.confidence}`}>
          Confidence: {insight.confidence}
        </div>
      </div>

      <div className="recommendation-section">
        <h4><ClipboardList size={15} /> Evidence summary</h4>
        <ul>
          {insight.evidence.slice(0, 6).map((item) => (
            <li key={`${item.label}-${item.value}`}>
              <strong>{item.label}</strong>
              <span>{item.value}</span>
              <small>{item.source}</small>
            </li>
          ))}
        </ul>
      </div>

      {insight.precedent_cases.length > 0 && (
        <div className="recommendation-section">
          <h4><History size={15} /> Precedent context</h4>
          <div className="precedent-list">
            {insight.precedent_cases.map((item) => (
              <article key={item.pattern}>
                <strong>{item.pattern}</strong>
                <span>
                  {item.similar_count} similar patterns · {item.escalated_to_sar_pct}% escalated to SAR
                </span>
                <small>{item.typical_outcome}</small>
              </article>
            ))}
          </div>
        </div>
      )}

      <div className="recommendation-section">
        <h4><Route size={15} /> Routing suggestion</h4>
        <p className="routing-line">
          <strong>{insight.routing_suggestion.team}</strong>
          <span>{insight.routing_suggestion.queue} · {insight.routing_suggestion.jurisdiction}</span>
          <small>{insight.routing_suggestion.workload_note}</small>
        </p>
      </div>

      <div className="recommendation-section draft-section">
        <h4><GitBranch size={15} /> Draft investigator notes</h4>
        <div className="draft-banner">{insight.draft_disclaimer}</div>
        <textarea
          value={draftNotes}
          onChange={(event) => setDraftNotes(event.target.value)}
          disabled={decided || deciding}
          rows={6}
          aria-label="Editable draft investigator notes"
        />
      </div>

      {insight.reasoning_trace.filter((item) => item.matched).length > 0 && (
        <details className="reasoning-trace">
          <summary>Reasoning trace (rule audit)</summary>
          <ul>
            {insight.reasoning_trace.filter((item) => item.matched).map((item) => (
              <li key={item.rule_id}>
                <strong>{item.rule_id}</strong>
                <span>{item.note}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {decisionError && <div className="inline-error">{decisionError}</div>}

      {decided ? (
        <div className={`decision-result decision-result--${insight.status}`}>
          {insight.status === "approved" ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
          <span>
            Recommendation {insight.status}. No downstream action was automated — human confirmation only.
          </span>
        </div>
      ) : (
        <div className="recommendation-actions">
          <button
            className="ui-button ui-button--primary ui-button--default"
            disabled={deciding}
            onClick={() => onApprove(draftNotes)}
          >
            <CheckCircle2 size={16} />
            Approve recommendation
          </button>
          <button
            className="ui-button ui-button--outline ui-button--default"
            disabled={deciding}
            onClick={() => setShowOverride((current) => !current)}
          >
            <XCircle size={16} />
            Override
          </button>
        </div>
      )}

      {showOverride && !decided && (
        <div className="override-form">
          <label>
            Reason code
            <select value={reasonCode} onChange={(event) => setReasonCode(event.target.value)}>
              {OVERRIDE_REASONS.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </label>
          <label>
            Why override? (audit trail — not performance scoring)
            <textarea
              value={freeText}
              onChange={(event) => setFreeText(event.target.value)}
              rows={3}
              placeholder="Document the decision-quality rationale…"
            />
          </label>
          <button
            className="ui-button ui-button--primary ui-button--default"
            disabled={deciding || !freeText.trim()}
            onClick={() => onOverride(draftNotes, reasonCode, freeText.trim())}
          >
            Submit override
          </button>
        </div>
      )}

      <small className="recommendation-meta">
        Generated {new Date(insight.generated_at).toLocaleString()} · Status: {insight.status}
      </small>
    </div>
  );
}
