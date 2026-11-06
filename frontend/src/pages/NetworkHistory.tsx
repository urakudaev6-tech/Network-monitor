import { formatServerDate } from "../utils/serverTime";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

type Scan = { id: number; subnet: string; scanned_at: string; total: number; detected: number; not_detected: number };
type Device = { ip: string; detected: boolean; mac: string | null; hostname: string | null };
type Event = { id: number; scan_id: number; ip: string; kind: string; old_value: string | null; new_value: string | null };
type Details = Scan & { devices: Device[]; events: Event[] };
type Change = { ip: string; previous?: Device; current?: Device };
const labels: Record<string, string> = { new_ip: "Новый IP", detected_again: "Снова обнаружен", mac_changed: "Изменился MAC", hostname_changed: "Изменилось имя" };

async function json<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

function compareDevices(previous: Details, current: Details) {
  const old = new Map(previous.devices.map(d => [d.ip, d]));
  const now = new Map(current.devices.map(d => [d.ip, d]));
  const lost: Change[] = [];
  const gained: Change[] = [];
  const macChanged: Change[] = [];
  const hostnameChanged: Change[] = [];
  for (const [ip, before] of old) {
    const after = now.get(ip);
    if (before.detected && (!after || !after.detected)) lost.push({ ip, previous: before, current: after });
    if (before.detected && after?.detected) {
      if (before.mac && after.mac && before.mac.toLowerCase() !== after.mac.toLowerCase()) macChanged.push({ ip, previous: before, current: after });
      if (before.hostname && after.hostname && before.hostname !== after.hostname) hostnameChanged.push({ ip, previous: before, current: after });
    }
  }
  for (const [ip, after] of now) {
    if (after.detected && !old.get(ip)?.detected) gained.push({ ip, previous: old.get(ip), current: after });
  }
  const sort = (a: Change, b: Change) => a.ip.localeCompare(b.ip, undefined, { numeric: true });
  return { lost: lost.sort(sort), gained: gained.sort(sort), macChanged: macChanged.sort(sort), hostnameChanged: hostnameChanged.sort(sort) };
}

function HistoryChart({ scans, onSelect }: { scans: Scan[]; onSelect: (id: number) => void }) {
  const series = [...scans].sort((a, b) => a.id - b.id);
  if (!series.length) return <p className="text-sm text-slate-500">Нет данных для графика.</p>;
  const width = 800, height = 240, left = 45, right = 16, top = 20, bottom = 40;
  const max = Math.max(1, ...series.map(s => s.total));
  const x = (i: number) => left + (series.length === 1 ? (width - left - right) / 2 : i * (width - left - right) / (series.length - 1));
  const y = (value: number) => height - bottom - value * (height - top - bottom) / max;
  const points = series.map((s, i) => `${x(i)},${y(s.detected)}`).join(" ");
  return <div className="overflow-x-auto">
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="График количества обнаруженных устройств по сканированиям" className="w-full min-w-[480px]">
      {[0, .25, .5, .75, 1].map(frac => <g key={frac}>
        <line x1={left} x2={width - right} y1={y(max * frac)} y2={y(max * frac)} stroke="#e2e8f0" />
        <text x={left - 8} y={y(max * frac) + 4} textAnchor="end" fontSize="12" fill="#64748b">{Math.round(max * frac)}</text>
      </g>)}
      <polyline points={points} fill="none" stroke="#1d4ed8" strokeWidth="3" strokeLinejoin="round" />
      {series.map((s, i) => <g key={s.id}>
        <circle cx={x(i)} cy={y(s.detected)} r="5" fill="#1d4ed8" stroke="white" strokeWidth="2" />
        <text x={x(i)} y={height - 13} textAnchor="middle" fontSize="12" fill="#475569">#{s.id}</text>
        <title>{`Сканирование №${s.id}: ${s.detected} из ${s.total}`}</title>
      </g>)}
    </svg>
    <div className="flex flex-wrap gap-2 mt-2">{series.map(s => <button key={s.id} type="button" className="text-xs rounded border px-2 py-1 hover:bg-slate-100" onClick={() => onSelect(s.id)}>№{s.id}: {s.detected}</button>)}</div>
  </div>;
}

export function NetworkHistory() {
  const [scans, setScans] = useState<Scan[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [details, setDetails] = useState<Details | null>(null);
  const [compareId, setCompareId] = useState<number | null>(null);
  const [compareDetails, setCompareDetails] = useState<Details | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [subnetFilter, setSubnetFilter] = useState("");
  const [changeFilter, setChangeFilter] = useState<"lost" | "gained" | "macChanged" | "hostnameChanged">("lost");
  const [search, setSearch] = useState("");

  useEffect(() => {
    Promise.all([json<Scan[]>("/api/scanner/history?limit=100"), json<Event[]>("/api/scanner/events")])
      .then(([s, e]) => { setScans(s); setEvents(e); })
      .catch(e => setError(String(e))).finally(() => setLoading(false));
  }, []);

  const subnets = useMemo(() => [...new Set(scans.map(s => s.subnet))].sort(), [scans]);
  const visibleScans = useMemo(() => scans.filter(s => !subnetFilter || s.subnet === subnetFilter), [scans, subnetFilter]);
  const comparisonCandidates = useMemo(() => scans.filter(s => details && s.subnet === details.subnet && s.id !== details.id), [scans, details]);
  const changes = useMemo(() => details && compareDetails && details.subnet === compareDetails.subnet ? compareDevices(compareDetails, details) : null, [details, compareDetails]);
  const displayedChanges = useMemo(() => (changes?.[changeFilter] ?? []).filter(item => item.ip.includes(search.trim())), [changes, changeFilter, search]);
  const drop = details && compareDetails ? compareDetails.detected - details.detected : 0;
  const dropPercent = details && compareDetails && compareDetails.detected > 0 ? Math.round(1000 * drop / compareDetails.detected) / 10 : 0;
  const suspicious = drop >= 20 && dropPercent >= 25;

  async function openScan(id: number) {
    setError(""); setDetailLoading(true); setDetails(null); setCompareDetails(null); setCompareId(null);
    try {
      const selected = await json<Details>(`/api/scanner/history/${id}`);
      setDetails(selected);
      const previous = scans.filter(s => s.subnet === selected.subnet && s.id < id).sort((a, b) => b.id - a.id)[0];
      if (previous) {
        setCompareId(previous.id);
        setCompareDetails(await json<Details>(`/api/scanner/history/${previous.id}`));
      }
    } catch (e) { setError(String(e)); }
    finally { setDetailLoading(false); }
  }

  async function chooseComparison(value: string) {
    if (!details) return;
    if (!value) { setCompareId(null); setCompareDetails(null); return; }
    const id = Number(value);
    setDetailLoading(true); setError(""); setCompareDetails(null); setCompareId(id);
    try {
      const result = await json<Details>(`/api/scanner/history/${id}`);
      if (result.subnet !== details.subnet || result.id === details.id) throw new Error("Сравнивать можно только разные сканирования одной подсети.");
      setCompareDetails(result);
    } catch (e) { setCompareId(null); setError(String(e)); }
    finally { setDetailLoading(false); }
  }

  return <main className="mx-auto max-w-6xl p-6 space-y-7">
    <nav className="flex flex-wrap gap-5 text-blue-700 underline"><Link to="/scanner">← Сканер</Link><Link to="/">Главная</Link><Link to="/scanner/devices">Реестр устройств</Link></nav>
    <h1 className="text-3xl font-bold">История сети</h1>
    <p className="text-sm text-slate-600">Нет ответа на ping ≠ устройство отключено. Сравнение показывает изменение наблюдений, а не гарантированное изменение состояния устройств.</p>
    {error && <p role="alert" className="text-red-700">{error}</p>}{loading && <p>Загрузка…</p>}
    <section className="bg-white rounded-lg border p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold">Динамика обнаружения</h2>
        <label className="text-sm">Подсеть: <select aria-label="Подсеть для графика" className="ml-2 border rounded p-2" value={subnetFilter} onChange={e => { setSubnetFilter(e.target.value); setDetails(null); setCompareDetails(null); setCompareId(null); }}><option value="">Все подсети (без объединения)</option>{subnets.map(s => <option key={s} value={s}>{s}</option>)}</select></label></div>
      {!subnetFilter && subnets.length > 1 ? <p className="text-sm text-amber-800">Выбери подсеть, чтобы сравнивать сопоставимые результаты. Общий график не объединяет разные сети.</p> : <HistoryChart scans={visibleScans} onSelect={openScan} />}
    </section>
    <section><h2 className="text-xl font-semibold mb-3">Сканирования</h2>
      <div className="overflow-x-auto rounded border bg-white"><table className="w-full text-sm text-left"><thead className="bg-slate-100"><tr><th className="p-3">Дата</th><th className="p-3">Подсеть</th><th className="p-3">Обнаружено</th><th className="p-3">Действие</th></tr></thead><tbody>
        {visibleScans.map(s => <tr key={s.id} className="border-t"><td className="p-3">{formatServerDate(s.scanned_at)}</td><td className="p-3">{s.subnet}</td><td className="p-3">{s.detected} / {s.total}</td><td className="p-3"><button className="text-blue-700 underline" onClick={() => openScan(s.id)}>Просмотр и сравнение</button></td></tr>)}
      </tbody></table></div>{!loading && scans.length === 0 && <p className="mt-2">История пуста.</p>}</section>
    {detailLoading && <p role="status">Загрузка сравнения…</p>}
    {details && <section className="bg-white rounded-lg border p-4 space-y-4">
      <h2 className="text-xl font-semibold">Сканирование №{details.id}: {details.subnet}</h2>
      <label className="block text-sm">Сравнить со сканированием:
        <select className="block mt-1 border rounded p-2 max-w-full" aria-label="Сканирование для сравнения" value={compareId ?? ""} onChange={e => void chooseComparison(e.target.value)} disabled={detailLoading}>
          <option value="">Не сравнивать</option>{comparisonCandidates.map(s => <option key={s.id} value={s.id}>№{s.id} — {formatServerDate(s.scanned_at)} ({s.detected})</option>)}
        </select>
      </label>
      {changes && compareDetails && <>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {([ ["Было обнаружено", compareDetails.detected], ["Стало обнаружено", details.detected], ["Перестали отвечать", changes.lost.length], ["Начали отвечать", changes.gained.length] ] as const).map(([label, value]) => <div key={label} className="border rounded p-3"><div className="text-xs text-slate-600">{label}</div><div className="text-2xl font-semibold">{value}</div></div>)}
        </div>
        {suspicious && <p role="alert" className="rounded border border-red-300 bg-red-50 text-red-900 p-3">Резкое снижение ответов: −{drop} ({dropPercent}%). Возможны временные сетевые проблемы или ограничения ICMP. IP не считаются свободными.</p>}
        {compareDetails.id > details.id && <p className="text-sm text-amber-800">Сравнение с более поздним сканированием: направления изменений относятся к выбранному порядку, а не ко времени.</p>}
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm">Изменения: <select className="ml-2 border rounded p-2" value={changeFilter} onChange={e => setChangeFilter(e.target.value as typeof changeFilter)}>
            <option value="lost">Перестали отвечать ({changes.lost.length})</option><option value="gained">Начали отвечать ({changes.gained.length})</option><option value="macChanged">Изменился MAC ({changes.macChanged.length})</option><option value="hostnameChanged">Изменилось имя ({changes.hostnameChanged.length})</option>
          </select></label>
          <input className="border rounded p-2" aria-label="Поиск IP в изменениях" placeholder="Поиск IP" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <div className="overflow-x-auto max-h-80 overflow-y-auto border rounded"><table className="w-full text-sm text-left"><thead className="bg-slate-100 sticky top-0"><tr><th className="p-2">IP</th><th className="p-2">Ранее</th><th className="p-2">Сейчас</th></tr></thead><tbody>
          {displayedChanges.map(c => <tr key={c.ip} className="border-t"><td className="p-2 font-mono">{c.ip}</td><td className="p-2">{changeFilter === "macChanged" ? c.previous?.mac : changeFilter === "hostnameChanged" ? c.previous?.hostname : c.previous?.detected ? "Ответил" : "Нет ответа"}</td><td className="p-2">{changeFilter === "macChanged" ? c.current?.mac : changeFilter === "hostnameChanged" ? c.current?.hostname : c.current?.detected ? "Ответил" : "Нет ответа"}</td></tr>)}
        </tbody></table>{displayedChanges.length === 0 && <p className="p-3 text-sm text-slate-500">Совпадений нет.</p>}</div>
      </>}
      <h3 className="font-semibold">Все адреса выбранного сканирования</h3>
      <div className="overflow-x-auto rounded border max-h-80 overflow-y-auto"><table className="w-full text-sm text-left"><thead className="bg-slate-100 sticky top-0"><tr><th className="p-3">IP</th><th className="p-3">Ответ</th><th className="p-3">MAC</th><th className="p-3">Имя</th></tr></thead><tbody>
        {details.devices.map(d => <tr key={d.ip} className="border-t"><td className="p-3">{d.ip}</td><td className="p-3">{d.detected ? "Обнаружен" : "Нет ответа"}</td><td className="p-3">{d.mac ?? "—"}</td><td className="p-3">{d.hostname ?? "—"}</td></tr>)}
      </tbody></table></div>
    </section>}
    <section><h2 className="text-xl font-semibold mb-3">Последние события</h2>
      <div className="overflow-x-auto rounded border bg-white"><table className="w-full text-sm text-left"><thead className="bg-slate-100"><tr><th className="p-3">Скан №</th><th className="p-3">IP</th><th className="p-3">Событие</th><th className="p-3">Было → стало</th></tr></thead><tbody>
        {events.map(e => <tr key={e.id} className="border-t"><td className="p-3">{e.scan_id}</td><td className="p-3">{e.ip}</td><td className="p-3">{labels[e.kind] ?? e.kind}</td><td className="p-3">{e.old_value ?? "—"} → {e.new_value ?? "—"}</td></tr>)}
      </tbody></table></div>{!loading && events.length === 0 && <p className="mt-2">Изменений пока нет.</p>}</section>
  </main>;
}
