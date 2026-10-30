import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AddTargetForm } from "../components/AddTargetForm";
import { TargetTable } from "../components/TargetTable";
import { api } from "../api/targets";
import { ApiError } from "../api/client";

export function Dashboard() {
  const qc = useQueryClient();

  const targets = useQuery({
    queryKey: ["targets"],
    queryFn: api.listTargets,
    refetchInterval: 10_000,
  });

  const results = useQuery({
    queryKey: ["results"],
    queryFn: api.getResults,
    refetchInterval: 10_000,
  });

  const add = useMutation({
    mutationFn: api.addTarget,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["targets"] }),
  });

  const del = useMutation({
    mutationFn: api.deleteTarget,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["targets"] });
      qc.invalidateQueries({ queryKey: ["results"] });
    },
  });

  const run = useMutation({
    mutationFn: api.runMonitor,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["results"] }),
  });

  const list = targets.data ?? [];
  const res = results.data ?? [];
  const upCount = res.filter((r) => r.ok).length;
  const downCount = res.filter((r) => !r.ok).length;
  const unknownCount = Math.max(0, list.length - res.length);

  const addError =
    add.error instanceof ApiError ? add.error.message : add.error ? "Ошибка" : null;

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">
      <header className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold">Network Monitor</h1>
        <button
          onClick={() => run.mutate()}
          disabled={run.isPending || list.length === 0}
          className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
        >
          {run.isPending ? "Проверяю..." : "Проверить сейчас"}
        </button>
      </header>

      <section className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Устройств" value={list.length} />
        <Stat label="Доступны" value={upCount} color="text-green-700" />
        <Stat label="Недоступны" value={downCount} color="text-red-700" />
        <Stat label="Без проверки" value={unknownCount} color="text-slate-600" />
      </section>

      {targets.isError && (
        <div className="p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
          Не удалось загрузить список: {(targets.error as Error).message}
        </div>
      )}

      {targets.isLoading ? (
        <div className="p-6 text-center text-slate-500">Загружаю...</div>
      ) : (
        <TargetTable
          targets={list}
          results={res}
          onDelete={(id) => del.mutate(id)}
          isDeleting={del.isPending}
        />
      )}

      <AddTargetForm
        onSubmit={(payload) => add.mutate(payload)}
        isSubmitting={add.isPending}
        error={addError}
      />
    </div>
  );
}

function Stat({ label, value, color = "text-slate-900" }: {
  label: string; value: number; color?: string;
}) {
  return (
    <div className="bg-white rounded shadow p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`text-2xl font-semibold ${color}`}>{value}</div>
    </div>
  );
}