import { Activity, TrendingUp } from "lucide-react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AlertDetail } from "../lib/types";

const compact = (value: number) =>
  new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);

export function TransactionActivityChart({ activity, currency }: { activity: AlertDetail["activity"]; currency: string }) {
  const current = activity.at(-1);
  return (
    <section className="panel activity-panel" aria-labelledby="activity-heading">
      <div className="panel__heading">
        <div>
          <p className="eyebrow">Behaviour over time</p>
          <h2 id="activity-heading">Transaction activity and risk</h2>
        </div>
        <TrendingUp size={22} aria-hidden="true" />
      </div>
      {current && (
        <div className="activity-current">
          <Activity size={18} />
          <span>Current period <b>{current.period}</b></span>
          <strong>{compact(current.total_amount)} {currency}</strong>
          <small>{current.transaction_count} transactions · risk {current.risk_level.toFixed(0)}/100</small>
        </div>
      )}
      {activity.length ? (
        <div className="activity-chart">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={activity} margin={{ top: 12, right: 10, left: 2, bottom: 0 }}>
              <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="period" tick={{ fontSize: 10 }} />
              <YAxis yAxisId="amount" tickFormatter={compact} tick={{ fontSize: 10 }} />
              <YAxis yAxisId="risk" orientation="right" domain={[0, 100]} tick={{ fontSize: 10 }} />
              <Tooltip
                formatter={(value, name) => [
                  name === "Risk level" ? `${Number(value).toFixed(0)}/100` : compact(Number(value)),
                  name,
                ]}
              />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Bar yAxisId="amount" dataKey="transaction_count" name="Transaction count" fill="#bfdbfe" radius={[4, 4, 0, 0]} />
              <Line yAxisId="amount" type="monotone" dataKey="total_amount" name={`Activity (${currency})`} stroke="#2563eb" strokeWidth={2.5} dot={false} />
              <Line yAxisId="risk" type="monotone" dataKey="risk_level" name="Risk level" stroke="#dc2626" strokeWidth={2} strokeDasharray="5 4" dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="empty-state"><p>No historical transaction activity is available.</p></div>
      )}
    </section>
  );
}
