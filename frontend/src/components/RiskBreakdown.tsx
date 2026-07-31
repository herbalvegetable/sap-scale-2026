import { ShieldCheck } from "lucide-react";
import type { FactorScore, RiskTier } from "../lib/types";
import { humanizeLabel } from "../lib/utils";

function formatEvidenceValue(label: string, value: string) {
  if (!/ratio/i.test(label) && !/×/.test(value)) return value;
  return value.replace(/(-?\d+(?:\.\d+)?)/g, (num) => {
    const parsed = Number(num);
    return Number.isFinite(parsed) ? parsed.toFixed(1) : num;
  });
}

export function RiskBreakdown({ factors }: { factors: FactorScore[] }) {
  return (
    <section className="panel" aria-labelledby="risk-breakdown-heading">
      <div className="panel__heading">
        <div>
          <p className="eyebrow">Auditable assessment</p>
          <h2 id="risk-breakdown-heading">Risk factor breakdown</h2>
        </div>
        <ShieldCheck size={22} aria-hidden="true" />
      </div>
      <div className="factor-list">
        {factors.map((factor) => {
          const percentage = (factor.score / factor.max_score) * 100;
          const level: RiskTier = percentage >= 67 ? "high" : percentage >= 34 ? "medium" : "low";
          const isTransactionBehaviour = factor.key === "transaction_behaviour";
          return (
            <article className={`factor factor--${level}`} key={factor.key}>
              <div className="factor__topline">
                <div>
                  <h3>{factor.label}</h3>
                  <span className={`factor-level factor-level--${level}`}>{level} risk</span>
                  <p>{factor.rationale}</p>
                </div>
                <strong>
                  {factor.score.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                  <span> / {factor.max_score.toLocaleString()}</span>
                </strong>
              </div>
              <div className="factor__bar" aria-label={`${factor.label}: ${factor.score} of ${factor.max_score}`}>
                <span className={`factor__fill factor__fill--${level}`} style={{ width: `${percentage}%` }} />
              </div>
              {factor.evidence.length > 0 && (
                <div className="evidence-row">
                  {factor.evidence.map((item) => (
                    <span className="evidence-chip" key={`${item.source}-${item.label}`}>
                      {humanizeLabel(item.label)} ({humanizeLabel(item.source)}):{" "}
                      <b>
                        {isTransactionBehaviour || /ratio/i.test(item.label)
                          ? formatEvidenceValue(item.label, item.value)
                          : item.value}
                      </b>
                    </span>
                  ))}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
