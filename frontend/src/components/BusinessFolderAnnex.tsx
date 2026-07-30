import { BookOpen, X } from "lucide-react";

const entries = [
  ["Threshold breach", "The alert scenario indicates that a monitored transaction value or pattern crossed a configured review threshold. It triggers review; it does not establish wrongdoing."],
  ["Baseline", "The entity's historical expected activity, including average transaction amount and monthly frequency. RiskAssess compares current behaviour with this reference point."],
  ["Amount ratio", "Current transaction amount divided by the entity's historical average amount. A value of 2.0 means the transaction is twice the baseline average."],
  ["Risk assessment breakdown", "Five bounded factor scores validated by the backend. The platform adds the factors to produce the final 0–100 priority."],
  ["Data confidence", "A rule-based data-quality flag for the priority score. It reflects completeness, match certainty, freshness, and corroboration of inputs — not how severe the risk is."],
  ["Beneficial owners", "Natural persons recorded as owning or controlling the entity. PEP and sanctions indicators are shown when supplied by HANA."],
  ["Risk intelligence", "A grounded explanation and suggested checks based on alert, entity, geography, and case evidence. It supports—but never replaces—human investigator judgement."],
];

export function BusinessFolderAnnex({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return (
    <>
      <button className="annex-backdrop" onClick={onClose} aria-label="Close glossary" />
      <aside className="annex-panel" aria-labelledby="annex-heading">
        <div className="annex-panel__heading">
          <div><BookOpen /><h2 id="annex-heading">Business Folder glossary</h2></div>
          <button onClick={onClose} aria-label="Close glossary"><X /></button>
        </div>
        <p>Plain-language definitions for the evidence and assessments shown on this page.</p>
        <dl>
          {entries.map(([term, definition]) => (
            <div key={term}><dt>{term}</dt><dd>{definition}</dd></div>
          ))}
        </dl>
      </aside>
    </>
  );
}
