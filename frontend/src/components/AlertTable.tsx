import { ArrowDownUp, ChevronRight, MapPin } from "lucide-react";
import type { AlertSummary, RiskTier } from "../lib/types";

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

export function TierBadge({ tier }: { tier: RiskTier }) {
  return <span className={`tier-badge tier-badge--${tier}`}>{tier}</span>;
}

interface Props {
  alerts: AlertSummary[];
  onSelect: (id: string) => void;
  onSort: () => void;
}

export function AlertTable({ alerts, onSelect, onSort }: Props) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>
              <button className="table-sort" onClick={onSort}>
                Risk <ArrowDownUp size={14} />
              </button>
            </th>
            <th>Alert & entity</th>
            <th>Transaction</th>
            <th>Route</th>
            <th>Status</th>
            <th>Raised</th>
            <th aria-label="Open alert" />
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert) => (
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
                  {alert.id} · {alert.alert_type}
                </span>
              </td>
              <td>
                <strong className="table-primary">{currency(alert.amount, alert.currency)}</strong>
                <span className="table-secondary">{alert.transaction_id}</span>
              </td>
              <td>
                <span className="route">
                  <MapPin size={14} aria-hidden="true" />
                  {alert.origin_country} → {alert.destination_country}
                </span>
              </td>
              <td>
                <span className="status-dot">
                  <i className={alert.status.toLowerCase().includes("review") ? "amber" : "red"} />
                  {alert.status}
                </span>
              </td>
              <td>{relativeTime(alert.created_at)}</td>
              <td>
                <ChevronRight size={18} aria-hidden="true" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {alerts.length === 0 && (
        <div className="empty-state">
          <h3>No alerts match these filters</h3>
          <p>Try a different risk tier or search term.</p>
        </div>
      )}
    </div>
  );
}
