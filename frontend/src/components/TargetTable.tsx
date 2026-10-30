import { Link } from "react-router-dom";
import type { MonitorResult, Target } from "../types";
import { StatusBadge } from "./StatusBadge";

interface Props {
  targets: Target[];
  results: MonitorResult[];
  onDelete: (id: number) => void;
  isDeleting?: boolean;
}

export function TargetTable({ targets, results, onDelete, isDeleting }: Props) {
  const byId = new Map(results.map((r) => [r.id, r]));

  if (targets.length === 0) {
    return (
      <div className="p-8 text-center text-slate-500 bg-white rounded shadow">
        Устройств пока нет. Добавь первое через форму ниже.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto bg-white rounded shadow">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-100 text-slate-700">
          <tr>
            <th className="px-3 py-2 text-left">ID</th>
            <th className="px-3 py-2 text-left">Хост</th>
            <th className="px-3 py-2 text-left">Тип</th>
            <th className="px-3 py-2 text-left">Порт</th>
            <th className="px-3 py-2 text-left">Задержка</th>
            <th className="px-3 py-2 text-left">Статус</th>
            <th className="px-3 py-2 text-right">Действия</th>
          </tr>
        </thead>
        <tbody>
          {targets.map((t) => {
            const r = byId.get(t.id);
            const status = !r ? "UNKNOWN" : r.ok ? "UP" : "DOWN";
            return (
              <tr key={t.id} className="border-t hover:bg-slate-50">
                <td className="px-3 py-2">{t.id}</td>
                <td className="px-3 py-2">
                  <Link to={`/targets/${t.id}`} className="text-blue-600 hover:underline">
                    {t.host}
                  </Link>
                </td>
                <td className="px-3 py-2 uppercase">{t.type}</td>
                <td className="px-3 py-2">{t.port ?? "—"}</td>
                <td className="px-3 py-2">
                  {r?.ms != null ? `${r.ms.toFixed(2)} мс` : "—"}
                </td>
                <td className="px-3 py-2"><StatusBadge status={status} /></td>
                <td className="px-3 py-2 text-right">
                  <button
                    onClick={() => {
                      if (confirm(`Удалить ${t.host}?`)) onDelete(t.id);
                    }}
                    disabled={isDeleting}
                    className="text-red-600 hover:text-red-800 text-xs disabled:opacity-50"
                  >
                    Удалить
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}