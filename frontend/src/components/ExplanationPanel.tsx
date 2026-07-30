import { BrainCircuit, CheckCircle2, FileSearch, Info, RefreshCw } from "lucide-react";
import type { Explanation } from "../lib/types";

interface Props {
  explanation?: Explanation;
  loading: boolean;
  refreshing: boolean;
  onRefresh: () => void;
}

export function ExplanationPanel({ explanation, loading, refreshing, onRefresh }: Props) {
  return (
    <section className="panel intelligence-panel" aria-labelledby="intelligence-heading">
      <div className="panel__heading">
        <div>
          <p className="eyebrow">SAP AI Core · GPT-4o</p>
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
            <BrainCircuit size={24} aria-hidden="true" />
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
          <div className="model-note">
            <Info size={15} />
            <span>
              {explanation.model} · {explanation.provenance} · {explanation.prompt_version}.
              Human review is required.
            </span>
          </div>
        </>
      ) : (
        <div className="empty-state"><p>No explanation is available.</p></div>
      )}
    </section>
  );
}
