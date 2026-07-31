import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Clock3, Filter, Search, SearchCheck, ShieldAlert, X } from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { api } from "../lib/api";
import { humanizeLabel } from "../lib/utils";
import {
  AlertTable,
  buildCaseFilterOptions,
  CASE_FILTER_FIELDS,
  EMPTY_CASE_FILTERS,
  type CaseFilters,
} from "./AlertTable";
import { Button } from "./ui/button";

interface Props {
  onSelectAlert: (id: string) => void;
  investigationsOnly?: boolean;
}

export function Dashboard({ onSelectAlert, investigationsOnly = false }: Props) {
  const [search, setSearch] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filters, setFilters] = useState<CaseFilters>(EMPTY_CASE_FILTERS);
  const filterRef = useRef<HTMLDivElement>(null);
  const sortOrder = "desc" as const;
  const stats = useQuery({ queryKey: ["stats"], queryFn: api.stats });
  const alerts = useQuery({
    queryKey: ["alerts", search, sortOrder, investigationsOnly],
    queryFn: () => api.alerts({
      search,
      sortOrder,
      pageSize: 100,
      status: investigationsOnly ? "investigating" : undefined,
    }),
  });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: 1 });

  const alertItems = alerts.data?.items ?? [];
  const filterOptions = useMemo(() => buildCaseFilterOptions(alertItems), [alertItems]);
  const activeFilterCount = Object.values(filters).filter(Boolean).length;

  useEffect(() => {
    if (!filtersOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (filterRef.current && !filterRef.current.contains(event.target as Node)) {
        setFiltersOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFiltersOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [filtersOpen]);

  const setFilter = (key: keyof CaseFilters, value: string) =>
    setFilters((current) => ({ ...current, [key]: value }));

  const chartData = stats.data
    ? [
        { name: "High", value: stats.data.high, color: "#dc2626" },
        { name: "Medium", value: stats.data.medium, color: "#f59e0b" },
        { name: "Low", value: stats.data.low, color: "#10b981" },
      ]
    : [];

  return (
    <main className="page-shell">
      <header className="page-header">
        <div>
          <p className="eyebrow">{investigationsOnly ? "Active casework" : "Financial crime operations"}</p>
          <h1>{investigationsOnly ? "Investigations" : "Case command centre"}</h1>
          <p>
            {investigationsOnly
              ? "Review every case currently under active investigation."
              : "Prioritise SLA-breached and high-tier cases first — the scored queue is the triage subset of the ops backlog."}
          </p>
        </div>
        <div className="live-indicator">
          <i />
          {health.data?.data_mode === "hana" ? "Live SAP HANA data" : "Resilient demo data"}
        </div>
      </header>

      {health.data?.status === "degraded" && (
        <div className="notice" role="status">
          <AlertTriangle size={18} />
          <span>
            Degraded mode: {health.data.data_mode === "demo" ? "demo data is active" : "scoring is running in limited mode"}.
            Case detail pages still show factor evidence and assessment status.
          </span>
        </div>
      )}

      <section className="metric-grid" aria-label="Case queue overview">
        <article className="metric-card metric-card--primary">
          <span className="metric-icon"><ShieldAlert /></span>
          <div>
            <p>Total cases</p>
            <strong>{stats.data?.total ?? "—"}</strong>
            <span>{stats.data?.open_alerts ?? "—"} require review</span>
          </div>
        </article>
        <article className="metric-card">
          <span className="metric-icon metric-icon--danger"><AlertTriangle /></span>
          <div>
            <p>High priority</p>
            <strong>{stats.data?.high ?? "—"}</strong>
            <span>Review first</span>
          </div>
        </article>
        <article className="metric-card">
          <span className="metric-icon metric-icon--neutral"><SearchCheck /></span>
          <div>
            <p>Investigating</p>
            <strong>{stats.data?.investigating ?? "—"}</strong>
            <span>Active team casework</span>
          </div>
        </article>
        <article className="metric-card">
          <span className="metric-icon metric-icon--neutral"><Clock3 /></span>
          <div>
            <p>Review target</p>
            <strong>&lt; 24h</strong>
            <span>Down from 1–3 days</span>
          </div>
        </article>
        <article className="metric-card metric-card--chart">
          <div>
            <p>Risk distribution</p>
            <span>Queue composition</span>
          </div>
          <div className="mini-chart">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={chartData} innerRadius={22} outerRadius={34} dataKey="value" paddingAngle={4}>
                  {chartData.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </article>
      </section>

      <section className="panel queue-panel">
        <div className="queue-header">
          <div>
            <p className="eyebrow">{investigationsOnly ? "Read-only workflow view" : "Prioritised queue"}</p>
            <h2>{investigationsOnly ? "Cases under investigation" : "Transaction cases"}</h2>
          </div>
          <div className="queue-controls">
            <label className="search-box">
              <Search size={17} aria-hidden="true" />
              <span className="sr-only">Search alerts</span>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search entity, alert or transaction"
              />
            </label>
            <div className="filter-control" ref={filterRef}>
              <button
                type="button"
                className={`filter-button ${filtersOpen || activeFilterCount > 0 ? "active" : ""}`}
                onClick={() => setFiltersOpen((open) => !open)}
                aria-expanded={filtersOpen}
                aria-haspopup="dialog"
              >
                <Filter size={15} />
                Filters
                {activeFilterCount > 0 && <span className="filter-button__count">{activeFilterCount}</span>}
              </button>
              {filtersOpen && (
                <div className="filter-panel" role="dialog" aria-label="Filter transaction cases">
                  <div className="filter-panel__header">
                    <div>
                      <strong>Filter cases</strong>
                      <p>Select from values present in the current queue.</p>
                    </div>
                    <div className="filter-panel__actions">
                      {activeFilterCount > 0 && (
                        <button type="button" onClick={() => setFilters(EMPTY_CASE_FILTERS)}>
                          Clear all
                        </button>
                      )}
                      <button
                        type="button"
                        className="filter-panel__close"
                        onClick={() => setFiltersOpen(false)}
                        aria-label="Close filters"
                      >
                        <X size={15} />
                      </button>
                    </div>
                  </div>
                  <div className="filter-panel__grid">
                    {CASE_FILTER_FIELDS.map(({ key, label }) => (
                      <label key={key} className="filter-field">
                        <span>{label}</span>
                        <select
                          value={filters[key]}
                          onChange={(event) => setFilter(key, event.target.value)}
                        >
                          <option value="">All</option>
                          {filterOptions[key].map((option) => (
                            <option key={option} value={option}>
                              {key === "alertType" || key === "risk" || key === "status"
                                ? humanizeLabel(option)
                                : option}
                            </option>
                          ))}
                        </select>
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
        {alerts.isLoading ? (
          <div className="loading-state"><span className="spinner" /> Loading prioritised alerts…</div>
        ) : alerts.isError ? (
          <div className="error-state">
            <AlertTriangle />
            <h3>Could not load alerts</h3>
            <p>{alerts.error.message}</p>
            <Button onClick={() => alerts.refetch()}>Try again</Button>
          </div>
        ) : (
          <AlertTable
            alerts={alertItems}
            filters={filters}
            onSelect={onSelectAlert}
          />
        )}
      </section>
    </main>
  );
}
