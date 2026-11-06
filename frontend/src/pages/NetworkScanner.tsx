import { formatServerDate } from "../utils/serverTime";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

type Device = {
  ip: string;
  detected: boolean;
  mac: string | null;
  hostname: string | null;
  latency_ms: number | null;
  error: string | null;
};
type ScanResponse = {
  subnet: string;
  scanned_at: string;
  total: number;
  detected: number;
  not_detected: number;
  devices: Device[];
  warning: string;
  quality?: {
    previous_detected: number | null;
    drop_count: number;
    drop_percent: number;
    suspicious: boolean;
  };
};
type Row = Device & { reserved: boolean };
type Filter = "all" | "online" | "offline" | "reserved";

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function makeRows(data: ScanResponse): Row[] {
  const parts = data.subnet.split("/");
  const prefix = parts[0].split(".").slice(0, 3).join(".");
  const mask = Number(parts[1]);
  if (mask !== 24 || !/^\d+\.\d+\.\d+$/.test(prefix)) {
    return data.devices.map((d) => ({ ...d, reserved: false }));
  }
  const byIp = new Map(data.devices.map((d) => [d.ip, d]));
  return Array.from({ length: 256 }, (_, last) => {
    const ip = `${prefix}.${last}`;
    const reserved = last === 0 || last === 255;
    return {
      ip,
      detected: false,
      mac: null,
      hostname: null,
      latency_ms: null,
      error: null,
      ...byIp.get(ip),
      reserved,
    };
  });
}

export function NetworkScanner() {
  const [subnet, setSubnet] = useState("192.168.100.0/24");
  const [timeout, setTimeoutValue] = useState("0.8");
  const [workers, setWorkers] = useState("32");
  const [retries, setRetries] = useState("1");
  const [data, setData] = useState<ScanResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [mailBusy, setMailBusy] = useState(false);
  const [mailStatus, setMailStatus] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const rows = useMemo(() => (data ? makeRows(data) : []), [data]);
  const candidates = useMemo(() => rows.filter((row) => !row.reserved && !row.detected), [rows]);
  const filtered = useMemo(() => rows.filter((row) => {
    const matches = [row.ip, row.hostname ?? "", row.mac ?? ""].some((value) =>
      value.toLowerCase().includes(search.trim().toLowerCase())
    );
    const matchesFilter = filter === "all" ||
      (filter === "reserved" && row.reserved) ||
      (filter === "online" && !row.reserved && row.detected) ||
      (filter === "offline" && !row.reserved && !row.detected);
    return matches && matchesFilter;
  }), [rows, search, filter]);

  function exportCandidates() {
    const csv = ["IP;Статус", ...candidates.map((row) => `${row.ip};Возможно свободен`)].join("\r\n");
    const blob = new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `ip-candidates-${data?.subnet.replace("/", "-") ?? "network"}.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  async function emailReport() {
    setMailBusy(true);
    setMailStatus("");
    try {
      const response = await fetch("/api/scanner/email-report", { method: "POST" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
      setMailStatus(`Письмо отправлено. Возможно свободных IP: ${body.candidates}.`);
    } catch (err) {
      setMailStatus(`Ошибка отправки: ${errorText(err)}`);
    } finally {
      setMailBusy(false);
    }
  }

  async function scan() {
    const parsedTimeout = Number(timeout);
    const parsedWorkers = Number(workers);
    const parsedRetries = Number(retries);

    if (!Number.isInteger(parsedWorkers) || parsedWorkers < 1 || parsedWorkers > 64 ||
        !Number.isInteger(parsedRetries) || parsedRetries < 0 || parsedRetries > 2 ||
        !workers.trim() || !retries.trim()) {
      setError("Workers must be 1-64 and retries must be 0-2.");
      return;
    }
    if (!Number.isFinite(parsedTimeout) || parsedTimeout < 0.2 || parsedTimeout > 5) {
      setError("Тайм-аут должен быть от 0.2 до 5 секунд.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const response = await fetch("/api/scanner/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subnet: subnet.trim(),
          timeout: parsedTimeout,
          workers: parsedWorkers,
          retries: parsedRetries,
        }),
      });
      if (!response.ok) {
        const details: unknown = await response.json().catch(() => null);
        const message = details && typeof details === "object" && "detail" in details
          ? JSON.stringify((details as { detail: unknown }).detail)
          : response.statusText;
        throw new Error(`HTTP ${response.status}: ${message}`);
      }
      const result = (await response.json()) as ScanResponse;
      setData(result);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="mx-auto max-w-6xl px-6 pt-5"><Link to="/scanner/history" className="text-blue-700 underline">История сканирований и события →</Link> <Link to="/scanner/devices" className="ml-5 text-blue-700 underline">Реестр устройств →</Link></div>
    <main className="max-w-7xl mx-auto p-4 sm:p-6 space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link to="/" className="text-sm text-blue-700 hover:underline">← Мониторинг устройств</Link>
          <h1 className="text-2xl font-bold mt-2">Сканер сети</h1>
          <p className="text-sm text-slate-500">Поиск устройств в разрешённой IPv4-подсети</p>
        </div>
      </header>

      <section className="bg-white rounded-lg shadow p-4 space-y-3">
        <div className="grid gap-3 sm:grid-cols-[minmax(180px,1fr)_120px_110px_110px_auto] sm:items-end">
          <label className="text-sm font-medium">Подсеть CIDR
            <input className="mt-1 w-full border rounded px-3 py-2 font-mono" value={subnet}
              onChange={(e) => setSubnet(e.target.value)} disabled={loading} />
          </label>
          <label className="text-sm font-medium">Тайм-аут (сек)
            <input className="mt-1 w-full border rounded px-3 py-2" type="number" min="0.2" max="5" step="0.1"
              value={timeout} onChange={(e) => setTimeoutValue(e.target.value)} disabled={loading} />
          </label>
          <label className="text-sm font-medium">Потоки
            <input className="mt-1 w-full border rounded px-3 py-2"
              type="number" min="1" max="64" step="1"
              value={workers} onChange={(e) => setWorkers(e.target.value)}
              disabled={loading} />
          </label>
          <label className="text-sm font-medium">Повторы
            <select className="mt-1 w-full border rounded px-3 py-2"
              value={retries} onChange={(e) => setRetries(e.target.value)}
              disabled={loading}>
              <option value="0">0</option>
              <option value="1">1</option>
              <option value="2">2</option>
            </select>
          </label>
          <button type="button" onClick={scan} disabled={loading || !subnet.trim()}
            className="bg-blue-700 text-white rounded px-5 py-2 hover:bg-blue-800 disabled:opacity-50">
            {loading ? "Сканирование..." : "Сканировать"}
          </button>
        </div>
        <p className="text-xs text-slate-500">Сервер разрешает сканирование только сетей из SCAN_ALLOWED_CIDRS. Повторный запуск обновит результаты.</p>
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" onClick={emailReport} disabled={mailBusy || loading}
            className="border border-blue-700 text-blue-700 rounded px-4 py-2 disabled:opacity-50">
            {mailBusy ? "Сканирование и отправка..." : "Сканировать и отправить на Gmail"}
          </button>
          <span role="status" className="text-sm text-slate-600">{mailStatus}</span>
        </div>
        {error && <p role="alert" className="bg-red-50 border border-red-200 text-red-700 p-3 rounded text-sm">{error}</p>}
      </section>

      {data && <>
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            ["Адресов проверено", data.total],
            ["Обнаружено", data.detected],
            ["Возможно свободны", candidates.length],
            ["Зарезервировано (/24)", data.subnet.endsWith("/24") ? 2 : "—"],
          ].map(([label, value]) => <div key={label} className="bg-white rounded-lg shadow p-4">
            <div className="text-xs text-slate-500">{label}</div>
            <div className="text-2xl font-bold mt-1">{value}</div>
          </div>)}
        </section>
        <div className="text-sm text-slate-600">
          Подсеть: <strong>{data.subnet}</strong> · Проверено: {formatServerDate(data.scanned_at)}
        </div>
        {data.quality?.suspicious && (
          <section role="alert" className="bg-red-50 border border-red-300 text-red-900 rounded p-4">
            <strong>Warning: unusual scan result.</strong>{" "}
            Previously detected: {data.quality.previous_detected}; now: {data.detected}.
            Drop: {data.quality.drop_count} ({data.quality.drop_percent}%).
            This does not mean those IP addresses are free or devices are offline.
          </section>
        )}
        <section className="bg-white rounded-lg shadow p-4 text-sm space-y-1">
          <h2 className="font-semibold">Scan diagnostics</h2>
          <p>Responded: {data.detected}; no ICMP response or probe error: {data.not_detected}.</p>
          <p>Exact causes cannot be established from a failed ping alone.</p>
          {data.quality?.previous_detected != null && !data.quality.suspicious && (
            <p>Previous detected count: {data.quality.previous_detected}.</p>
          )}
        </section>
        <p className="text-sm bg-amber-50 border border-amber-200 text-amber-900 rounded p-3">
          <strong>Важно:</strong> «Возможно свободен» означает только отсутствие ответа при сканировании. Перед назначением адреса проверь DHCP-пул, резервации и ARP на маршрутизаторе. Адреса сети и broadcast исключены. {data.warning}
        </p>
        <section className="bg-white rounded-lg shadow p-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-semibold">Кандидаты на свободные IP</h2>
            <p className="text-sm text-slate-500">Не обнаружены при последнем сканировании: {candidates.length}. Это не подтверждение доступности для назначения.</p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <button type="button" onClick={() => setFilter("offline")} className="bg-blue-700 text-white rounded px-4 py-2 hover:bg-blue-800">Показать кандидатов</button>
            <button type="button" onClick={exportCandidates} disabled={candidates.length === 0} className="border rounded px-4 py-2 hover:bg-slate-50 disabled:opacity-50">Скачать CSV</button>
          </div>
        </section>
        <section className="bg-white rounded-lg shadow overflow-hidden">
          <div className="p-4 flex flex-wrap items-center justify-between gap-3 border-b">
            <input aria-label="Поиск по IP, имени или MAC" placeholder="Поиск по IP, имени или MAC" value={search}
              onChange={(e) => setSearch(e.target.value)} className="border rounded px-3 py-2 w-full sm:w-72" />
            <select aria-label="Фильтр статуса" value={filter} onChange={(e) => setFilter(e.target.value as Filter)}
              className="border rounded px-3 py-2">
              <option value="all">Все адреса</option>
              <option value="online">Обнаружены</option>
              <option value="offline">Возможно свободны</option>
              <option value="reserved">Зарезервированы</option>
            </select>
            <span className="text-xs text-slate-500">Показано: {filtered.length}</span>
          </div>
          <div className="overflow-x-auto max-h-[65vh] overflow-y-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-100 sticky top-0"><tr>
                {['IP-адрес', 'Имя устройства', 'MAC', 'Задержка', 'Статус'].map((name) =>
                  <th key={name} className="text-left px-3 py-2 whitespace-nowrap">{name}</th>)}
              </tr></thead>
              <tbody>{filtered.map((row) => <tr key={row.ip} className="border-t hover:bg-slate-50">
                <td className="px-3 py-2 font-mono whitespace-nowrap">{row.ip}</td>
                <td className="px-3 py-2">{row.reserved ? (row.ip.endsWith('.0') ? 'Network' : 'Broadcast') : row.hostname ?? '—'}</td>
                <td className="px-3 py-2 font-mono whitespace-nowrap">{row.mac ?? '—'}</td>
                <td className="px-3 py-2 whitespace-nowrap">{row.latency_ms == null ? '—' : `${row.latency_ms.toFixed(2)} мс`}</td>
                <td className="px-3 py-2"><span className={`inline-block px-2 py-1 rounded text-xs whitespace-nowrap ${row.reserved ? 'bg-slate-100 text-slate-700' : row.detected ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'}`}>
                  {row.reserved ? 'Зарезервирован' : row.detected ? 'Обнаружен' : 'Возможно свободен'}
                </span></td>
              </tr>)}</tbody>
            </table>
            {filtered.length === 0 && <p className="p-6 text-center text-slate-500">Нет совпадений</p>}
          </div>
        </section>
      </>}
      {!data && !loading && <p className="text-center text-slate-500 py-8">Нажми «Сканировать», чтобы получить данные сети.</p>}
    </main>
    </>
  );
}
