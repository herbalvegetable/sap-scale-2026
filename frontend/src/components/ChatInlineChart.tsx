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
import type { ChatChartSpec } from "../lib/types";

const compact = (value: number) =>
  new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);

export function ChatInlineChart({ chart }: { chart: ChatChartSpec }) {
  return (
    <div className="chat-inline-chart" aria-label={chart.title}>
      <strong>{chart.title}</strong>
      <div className="chat-inline-chart__canvas">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chart.points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} layout={chart.chart_type === "factor_breakdown" ? "vertical" : "horizontal"}>
            <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" vertical={false} />
            {chart.chart_type === "factor_breakdown" ? (
              <>
                <XAxis type="number" tick={{ fontSize: 9 }} />
                <YAxis type="category" dataKey={chart.x_key} width={88} tick={{ fontSize: 9 }} />
              </>
            ) : (
              <>
                <XAxis dataKey={chart.x_key} tick={{ fontSize: 9 }} />
                <YAxis tickFormatter={compact} tick={{ fontSize: 9 }} />
              </>
            )}
            <Tooltip formatter={(value) => compact(Number(value))} />
            <Legend wrapperStyle={{ fontSize: 10 }} />
            {chart.series.map((series) =>
              series.type === "line" ? (
                <Line
                  key={series.key}
                  type="monotone"
                  dataKey={series.key}
                  name={series.label}
                  stroke="#2563eb"
                  dot={false}
                  strokeWidth={2}
                />
              ) : (
                <Bar key={series.key} dataKey={series.key} name={series.label} fill="#93c5fd" radius={[3, 3, 0, 0]} />
              ),
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <small>{chart.source}</small>
    </div>
  );
}
