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
            <li>Investigators remain accountable for final case disposition.</li>
          </ul>
        </div>
      </section>
    </main>
  );
}
