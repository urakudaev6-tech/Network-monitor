import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/targets";
import { LatencyChart } from "../components/LatencyChart";
import { StatusBadge } from "../components/StatusBadge";

export function TargetDetails() {
  const { id } = useParams<{ id: string }>();
  const targetId = Number(id);

  const target = useQuery({
    queryKey: ["target", targetId],
    queryFn: () => api.getTarget(targetId),
    enabled: Number.isFinite(targetId),
  });

  const history = useQuery({
    queryKey: ["history", targetId],
    queryFn: () => api.getHistory(targetId, 100),
    enabled: Number.isFinite(targetId),
    refetchInterval: 10_000,
  });

  if (target.isError) {
    return (
      <div className="max-w-4xl mx-auto p-6">
        <p className="text-red-700">Не удалось загрузить: {(target.error as Error).message}</p>
        <Link to="/" className="text-blue-600 hover:underline">← назад</Link>
      </div>
    );
  }

  if (target.isLoading || !target.data) {
    return <div className="max-w-4xl mx-auto p-6">Загружаю...</div>;
  }

  const t = target.data;
  const hist = history.data ?? [];
  const latest = hist[0];
  const status = !latest ? "UNKNOWN" : latest.ok ? "UP" : "DOWN";

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      <Link to="/" className="text-blue-600 hover:underline text-sm">← к списку</Link>

      <header className="bg-white rounded shadow p-4 space-y-2">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold">{t.host}</h1>
          <StatusBadge status={status} />
        </div>
        <div className="text-sm text-slate-600">
          Тип: <strong className="uppercase">{t.type}</strong>
          {t.port != null && <> · Порт: <strong>{t.port}</strong></>}
          {" · "}Тайм-аут: <strong>{t.timeout} с</strong>
        </div>
      </header>

      <LatencyChart history={hist} />

      <section className="bg-white rounded shadow">
        <h2 className="font-semibold p-4 border-b">История (последние 100)</h2>
        {hist.length === 0 ? (
          <div className="p-6 text-slate-500 text-center">
            Проверок ещё не было. Нажми «Проверить сейчас» на главной.
          </div>
        ) : (
          <table className="min-w-full text-sm">
            <thead className="bg-slate-100 text-slate-700">
              <tr>
                <th className="px-3 py-2 text-left">Время</th>
                <th className="px-3 py-2 text-left">OK</th>
                <th className="px-3 py-2 text-left">Задержка</th>
                <th className="px-3 py-2 text-left">Изменился</th>
                <th className="px-3 py-2 text-left">Ошибка</th>
              </tr>
            </thead>
            <tbody>
              {hist.map((r) => (
                <tr key={r.id} className="border-t">
                  <td className="px-3 py-2">{new Date(r.checked_at).toLocaleString()}</td>
                  <td className="px-3 py-2">
                    {r.ok ? <span className="text-green-700">да</span> :
                             <span className="text-red-700">нет</span>}
                  </td>
                  <td className="px-3 py-2">{r.ms != null ? `${r.ms.toFixed(2)} мс` : "—"}</td>
                  <td className="px-3 py-2">{r.status_changed ? "да" : "—"}</td>
                  <td className="px-3 py-2 text-slate-600">{r.error ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}