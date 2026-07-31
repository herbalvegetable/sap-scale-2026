import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { humanizeLabel } from "../lib/utils";

const FACTORS = [
  {
    name: "Entity risk profile",
    max: 25,
    sources: "Company risk profiles, beneficial owners, sanctions indicators",
    assesses: "Sanctions hits, PEP association, adverse media, ownership opacity, and KYC risk rating.",
  },
  {
    name: "Transaction behaviour",
    max: 25,
    sources: "Transactions",
    assesses: "Amount size relative to expected activity, structuring patterns, speed, and rapid-transfer behaviour.",
  },
  {
    name: "Geographic risk",
    max: 20,
    sources: "Countries / corridors",
    assesses: "FATF status and origin/destination country risk, including unusual high-risk corridors.",
  },
  {
    name: "Behavioural deviation",
    max: 15,
    sources: "Transactions and baselines",
    assesses: "How far the current amount, frequency, or corridor differs from the entity’s historical baseline.",
  },
  {
    name: "Regulatory sensitivity",
    max: 15,
    sources: "Compliance cases and supervisory context",
    assesses: "Supervisory attention on the corridor and prior compliance or SAR-related exposure.",
  },
] as const;

export function HelpGovernancePage() {
  const audit = useQuery({
    queryKey: ["audit", 20],
    queryFn: () => api.audit(20),
    refetchInterval: 15_000,
  });

  return (
    <main className="page-shell help-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Decision support</p>
          <h1>Help & governance</h1>
          <p>How RiskAssess builds a bounded 0–100 priority score and what each factor represents.</p>
        </div>
      </header>

      <section className="panel help-card">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">Formula</p>
            <h2>Priority score</h2>
          </div>
        </div>
          <div className="help-body">
          <p>
            RiskAssess scores five bounded risk factors from live HANA business context.
            The platform validates each factor, then <strong>adds the scores</strong> into a final priority from 0 to 100.
            Factor scores never replace the deterministic total.
          </p>
          <div className="help-formula" aria-label="Risk score formula">
            <code>Priority = Entity + Transaction + Geographic + Deviation + Regulatory</code>
            <span>Maximum = 25 + 25 + 20 + 15 + 15 = 100</span>
          </div>
          <div className="help-tiers">
            <article><strong>Low</strong><span>0 – 33</span></article>
            <article><strong>Medium</strong><span>34 – 66</span></article>
            <article><strong>High</strong><span>67 – 100</span></article>
          </div>
        </div>
      </section>

      <section className="panel help-card">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">Factor rubric</p>
            <h2>What each risk factor assesses</h2>
          </div>
        </div>
        <div className="help-factor-list">
          {FACTORS.map((factor) => (
            <article key={factor.name}>
              <div>
                <h3>{factor.name}</h3>
                <p>{factor.assesses}</p>
                <small>Primary sources: {factor.sources}</small>
              </div>
              <strong>{factor.max}<span>/ max</span></strong>
            </article>
          ))}
        </div>
      </section>

      <section className="panel help-card">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">Governance</p>
            <h2>Human review remains required</h2>
          </div>
        </div>
        <div className="help-body">
          <ul>
            <li>RiskAssess is decision support only. It does not block payments, file SARs, or determine guilt.</li>
            <li>Every score exposes factor evidence, assessment version, and generation time.</li>
            <li>When live data services are limited, deterministic scoring keeps the queue usable with clear status.</li>
            <li>Investigators remain accountable for final case disposition via Approve / Override controls.</li>
            <li>
              Model risk posture: prioritisation and decision-support follow lighter governance; any model that
              would autonomously change customer outcomes requires formal Model Risk Management validation first.
            </li>
          </ul>
        </div>
      </section>

      <section className="panel help-card">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">Privacy & security</p>
            <h2>Residency, prompt minimisation, injection controls</h2>
          </div>
        </div>
        <div className="help-body">
          <ul>
            <li>
              Customer data stays in approved regional environments — SAP BTP / HANA in
              {" "}{audit.data?.privacy?.region ?? "AP-Southeast (Singapore BTP)"}.
            </li>
            <li>
              Investigators see full case facts in the UI; generative prompts receive minimised / hashed
              identifiers and redacted free-text purposes ({audit.data?.privacy?.mode ?? "prompt_minimisation"}).
            </li>
            <li>
              User messages and retrieved policy passages are wrapped as untrusted data. Requests to clear,
              escalate, file a SAR, or freeze funds are refused — disposition stays on the recommendation card.
            </li>
          </ul>
        </div>
      </section>

      <section className="panel help-card">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">Data architecture</p>
            <h2>Normalisation and backlog triage</h2>
          </div>
        </div>
        <div className="help-body">
          <ul>
            <li>
              Live alerts are joined from HANA sources and normalised into a canonical status
              (open / investigating / closed) with SLA breach flags — siloed raw statuses stay visible as provenance.
            </li>
            <li>
              Backlog KPIs measure the full operations population. The scored work queue is the prioritised subset
              (SLA-breached and high-tier first) so remediation focuses on regulatory exposure before a full core replatform.
            </li>
          </ul>
        </div>
      </section>

      <section className="panel help-card">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">Audit trail</p>
            <h2>Recent human and guardrail events</h2>
          </div>
        </div>
        <div className="help-body">
          <p>
            Decisions and chat refusals append to a durable session audit log so restarts do not erase the demo trail.
          </p>
          {audit.isLoading && <p>Loading audit events…</p>}
          {audit.isError && <p>Audit feed unavailable in this session.</p>}
          {audit.data && audit.data.items.length === 0 && (
            <p>No decisions or chat refusals recorded yet. Approve or Override a recommendation to create one.</p>
          )}
          {audit.data && audit.data.items.length > 0 && (
            <ul className="help-audit-list">
              {audit.data.items.map((event) => (
                <li key={`${event.event_type}-${event.timestamp}-${event.summary}`}>
                  <strong>{humanizeLabel(event.event_type)}</strong>
                  <span>
                    {new Date(event.timestamp).toLocaleString()}
                    {event.alert_id ? ` · ${event.alert_id}` : ""}
                    {event.refused_action ? " · refused" : ""}
                  </span>
                  <small>{event.summary}</small>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </main>
  );
}
