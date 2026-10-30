import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CheckResult } from "../types";

interface Props {
  history: CheckResult[];
}

export function LatencyChart({ history }: Props) {
  // ms=null → не рисуем точку (connectNulls=false по умолчанию)
  const data = [...history]
    .reverse() // история приходит от новых к старым, для графика — наоборот
    .map((r) => ({
      time: new Date(r.checked_at).toLocaleTimeString(),
      ms: r.ms,
      ok: r.ok,
    }));

  if (data.length === 0) {
    return (
      <div className="p-6 text-center text-slate-500 bg-white rounded shadow">
        Нет данных для графика
      </div>
    );
  }

  return (
    <div className="bg-white rounded shadow p-4">
      <h2 className="font-semibold mb-2">Задержка (мс)</h2>
      <div style={{ width: "100%", height: 260 }}>
        <ResponsiveContainer>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Line
              type="monotone"
              dataKey="ms"
              stroke="#2563eb"
              dot={false}
              connectNulls={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}