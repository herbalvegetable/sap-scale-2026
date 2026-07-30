import { ShieldCheck } from "lucide-react";
import type { FactorScore } from "../lib/types";

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
          return (
            <article className="factor" key={factor.key}>
              <div className="factor__topline">
                <div>
                  <h3>{factor.label}</h3>
                  <p>{factor.rationale}</p>
                </div>
                <strong>
                  {factor.score.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                  <span> / {factor.max_score.toLocaleString()}</span>
                </strong>
              </div>
              <div className="factor__bar" aria-label={`${factor.label}: ${factor.score} of ${factor.max_score}`}>
                <span style={{ width: `${percentage}%` }} />
              </div>
              {factor.evidence.length > 0 && (
                <div className="evidence-row">
                  {factor.evidence.map((item) => (
                    <span className="evidence-chip" key={`${item.source}-${item.label}`}>
                      {item.label}: <b>{item.value}</b>
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
