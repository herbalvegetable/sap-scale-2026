import { useMemo, useState } from "react";
import {
  ArrowDownUp,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Clock3,
  MapPin,
  SearchCheck,
} from "lucide-react";
import type { AlertSummary } from "../lib/types";
import { humanizeLabel } from "../lib/utils";

const currency = (value: number, code: string) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: code,
    maximumFractionDigits: 0,
  }).format(value);

const relativeTime = (value: string) => {
  const hours = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 3_600_000));
  if (hours < 1) return "Less than 1h ago";
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
};

export function TierBadge({ tier }: { tier: AlertSummary["score"]["tier"] }) {
  return <span className={`tier-badge tier-badge--${tier}`}>{tier}</span>;
}

export type SortKey = "risk" | "entity" | "amount" | "route" | "status" | "raised";

export interface CaseFilters {
  risk: string;
  entity: string;
  alertType: string;
  amount: string;
  currency: string;
  transactionId: string;
  origin: string;
  destination: string;
  route: string;
  status: string;
  raised: string;
}

export const EMPTY_CASE_FILTERS: CaseFilters = {
  risk: "",
  entity: "",
  alertType: "",
  amount: "",
  currency: "",
  transactionId: "",
  origin: "",
  destination: "",
  route: "",
  status: "",
  raised: "",
};

export const CASE_FILTER_FIELDS: { key: keyof CaseFilters; label: string }[] = [
  { key: "risk", label: "Risk" },
  { key: "entity", label: "Entity" },
  { key: "alertType", label: "Alert type" },
  { key: "amount", label: "Amount" },
  { key: "currency", label: "Currency" },
  { key: "transactionId", label: "Transaction ID" },
  { key: "origin", label: "Origin" },
  { key: "destination", label: "Destination" },
  { key: "route", label: "Route" },
  { key: "status", label: "Status" },
  { key: "raised", label: "Raised" },
];

const isReviewTimeout = (reason: string | null | undefined) =>
  Boolean(
    reason &&
      (reason.includes("Manual review took too long") || reason.includes("Auto-timeout")),
  );

export function statusDisplay(alert: AlertSummary) {
  if (alert.status === "closed" && alert.status_reason) return alert.status_reason;
  return alert.status_label;
}

export function raisedDisplay(alert: AlertSummary) {
  return new Date(alert.created_at).toLocaleDateString();
}

export function routeDisplay(alert: AlertSummary) {
  return `${alert.origin_country} → ${alert.destination_country}`;
}

export function amountDisplay(alert: AlertSummary) {
  return currency(alert.amount, alert.currency);
}

function uniqueSorted(values: string[]) {
  return [...new Set(values.filter(Boolean))].sort((left, right) =>
    left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" }),
  );
}

export function buildCaseFilterOptions(alerts: AlertSummary[]): Record<keyof CaseFilters, string[]> {
  return {
    risk: uniqueSorted(alerts.map((alert) => alert.score.tier)),
    entity: uniqueSorted(alerts.map((alert) => alert.company_name)),
    alertType: uniqueSorted(alerts.map((alert) => alert.alert_type)),
    amount: uniqueSorted(alerts.map(amountDisplay)),
    currency: uniqueSorted(alerts.map((alert) => alert.currency)),
    transactionId: uniqueSorted(alerts.map((alert) => alert.transaction_id)),
    origin: uniqueSorted(alerts.map((alert) => alert.origin_country)),
    destination: uniqueSorted(alerts.map((alert) => alert.destination_country)),
    route: uniqueSorted(alerts.map(routeDisplay)),
    status: uniqueSorted(alerts.map(statusDisplay)),
    raised: uniqueSorted(alerts.map(raisedDisplay)),
  };
}

export function matchesCaseFilters(alert: AlertSummary, filters: CaseFilters) {
  return (
    (!filters.risk || alert.score.tier === filters.risk) &&
    (!filters.entity || alert.company_name === filters.entity) &&
    (!filters.alertType || alert.alert_type === filters.alertType) &&
    (!filters.amount || amountDisplay(alert) === filters.amount) &&
    (!filters.currency || alert.currency === filters.currency) &&
    (!filters.transactionId || alert.transaction_id === filters.transactionId) &&
    (!filters.origin || alert.origin_country === filters.origin) &&
    (!filters.destination || alert.destination_country === filters.destination) &&
    (!filters.route || routeDisplay(alert) === filters.route) &&
    (!filters.status || statusDisplay(alert) === filters.status) &&
    (!filters.raised || raisedDisplay(alert) === filters.raised)
  );
}

export function StatusBadge({ alert }: { alert: AlertSummary }) {
  const timedOut = isReviewTimeout(alert.status_reason);
  const Icon = alert.status === "closed"
    ? timedOut ? Clock3 : CheckCircle2
    : alert.status === "investigating" ? SearchCheck : CircleDot;
  return (
    <span className={`status-badge status-badge--${alert.status} ${timedOut ? "status-badge--timeout" : ""}`}>
      <Icon size={13} aria-hidden="true" />
      <span>
        <b>{alert.status_label}</b>
        {alert.status_reason && <small>{alert.status_reason.replace("Closed – ", "")}</small>}
      </span>
    </span>
  );
}

interface Props {
  alerts: AlertSummary[];
  filters?: CaseFilters;
  onSelect: (id: string) => void;
}

export function AlertTable({ alerts, filters = EMPTY_CASE_FILTERS, onSelect }: Props) {
  const [sort, setSort] = useState<{ key: SortKey; direction: "asc" | "desc" }>({
    key: "risk",
    direction: "desc",
  });

  const visibleAlerts = useMemo(() => {
    const filtered = alerts.filter((alert) => matchesCaseFilters(alert, filters));
    const factor = sort.direction === "asc" ? 1 : -1;
    return filtered.sort((left, right) => {
      const values: Record<SortKey, [string | number, string | number]> = {
        risk: [left.score.total, right.score.total],
        entity: [left.company_name, right.company_name],
        amount: [left.amount, right.amount],
        route: [left.destination_country, right.destination_country],
        status: [statusDisplay(left), statusDisplay(right)],
        raised: [new Date(left.created_at).getTime(), new Date(right.created_at).getTime()],
      };
      return values[sort.key][0] < values[sort.key][1] ? -factor : values[sort.key][0] > values[sort.key][1] ? factor : 0;
    });
  }, [alerts, filters, sort]);

  const toggleSort = (key: SortKey) =>
    setSort((current) => ({
      key,
      direction: current.key === key && current.direction === "desc" ? "asc" : "desc",
    }));

  const Header = ({ label, sortKey }: { label: string; sortKey: SortKey }) => (
    <button className="table-sort" onClick={() => toggleSort(sortKey)}>
      {label} <ArrowDownUp size={13} />
    </button>
  );

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th><Header label="Risk" sortKey="risk" /></th>
            <th><Header label="Alert & entity" sortKey="entity" /></th>
            <th><Header label="Transaction" sortKey="amount" /></th>
            <th><Header label="Route" sortKey="route" /></th>
            <th><Header label="Status" sortKey="status" /></th>
            <th><Header label="Raised" sortKey="raised" /></th>
            <th aria-label="Open alert" />
          </tr>
        </thead>
        <tbody>
          {visibleAlerts.map((alert) => (
            <tr
              key={alert.id}
              className="clickable-row"
              onClick={() => onSelect(alert.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") onSelect(alert.id);
              }}
              tabIndex={0}
            >
              <td>
                <div className={`score-pill score-pill--${alert.score.tier}`}>
                  <strong>{Math.round(alert.score.total)}</strong>
                  <TierBadge tier={alert.score.tier} />
                </div>
              </td>
              <td>
                <strong className="table-primary">{alert.company_name}</strong>
                <span className="table-secondary">
                  {alert.id} · {humanizeLabel(alert.alert_type)}
                </span>
              </td>
              <td>
                <strong className="table-primary">{currency(alert.amount, alert.currency)}</strong>
                <span className="table-secondary">{alert.transaction_id}</span>
              </td>
              <td>
                <span className="route">
                  <MapPin size={14} aria-hidden="true" />
                  {routeDisplay(alert)}
                </span>
              </td>
              <td>
                <StatusBadge alert={alert} />
              </td>
              <td>{relativeTime(alert.created_at)}</td>
              <td>
                <ChevronRight size={18} aria-hidden="true" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {visibleAlerts.length === 0 && (
        <div className="empty-state">
          <h3>No alerts match these filters</h3>
          <p>Clear one or more filters to broaden the results.</p>
        </div>
      )}
    </div>
  );
}
