import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { formatServerDate } from "../utils/serverTime";

type Rules = { missed_scans: number; new_ip: boolean; mac_changed: boolean; hostname_changed: boolean; detected_again: boolean; missed_ping: boolean };
type Alert = { id: string; kind: string; ip: string; scan_id: number; message: string; severity: string; acknowledged: boolean };
type Data = { rules: Rules; alerts: Alert[]; stats: { registered: number; responding_last_scan: number; not_responding_last_scan: number; scans: number; unacknowledged: number; last_scan: { scanned_at: string; subnet: string } | null }; notice: string };
const names: Record<string, string> = { new_ip: "Новый IP", mac_changed: "Смена MAC", hostname_changed: "Смена имени", detected_again: "Повторное обнаружение", missed_ping: "Нет ответа на ping" };
async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: "same-origin", ...init });
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${(await response.text()).slice(0, 200)}`);
  return response.json() as Promise<T>;
}
const button = "border border-slate-300 rounded-lg px-3 py-2 hover:bg-slate-100 disabled:opacity-40";
export function AlertCenter() {
  const [data, setData] = useState<Data | null>(null);
  const [rules, setRules] = useState<Rules | null>(null);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("active");
  const [severity, setSeverity] = useState("all");
  const [kind, setKind] = useState("all");
  const [query, setQuery] = useState("");
  const [grouped, setGrouped] = useState(true);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string[]>([]);
  const [showRules, setShowRules] = useState(false);
  const refresh = useCallback(async () => {
    try {
      const d = await api<Data>("/api/alerts");
      setData(d);
      setRules(old => old ?? d.rules);
      setError("");
    } catch (e) { setError(String(e)); }
  }, []);
  useEffect(() => { void refresh(); const timer = window.setInterval(() => void refresh(), 30000); return () => window.clearInterval(timer); }, [refresh]);
  useEffect(() => { setPage(1); setSelected([]); }, [filter, severity, kind, query, grouped]);
  async function saveRules() {
    if (!rules) return;
    setBusy(true);
    try {
      await api("/api/alerts/rules", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(rules) });
      setDirty(false); setNotice("Правила сохранены"); await refresh();
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function changeAck(ids: string[], acknowledged: boolean) {
    if (!ids.length) return;
    setBusy(true); setNotice("");
    try {
      const result = await api<{ updated: number }>("/api/alerts/bulk-ack", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids, acknowledged }) });
      setSelected([]); setNotice(`Обработано уведомлений: ${result.updated}`); await refresh();
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  const alerts = data?.alerts ?? [];
  const shown = useMemo(() => alerts.filter(a =>
    (filter === "all" || (filter === "active" ? !a.acknowledged : a.acknowledged)) &&
    (severity === "all" || a.severity === severity) &&
    (kind === "all" || a.kind === kind) &&
    (!query.trim() || `${a.ip} ${a.message} ${a.scan_id}`.toLowerCase().includes(query.trim().toLowerCase()))
  ), [alerts, filter, severity, kind, query]);
  type Group = { key: string; ip: string; kind: string; message: string; severity: string; scan_id: number; acknowledged: boolean; ids: string[]; count: number };
  const rows = useMemo<Group[]>(() => {
    if (!grouped) return shown.map(a => ({ ...a, key: a.id, ids: [a.id], count: 1 }));
    const groups = new Map<string, Group>();
    for (const a of shown) {
      const key = `${a.ip}|${a.kind}|${a.acknowledged}`;
      const existing = groups.get(key);
      if (existing) { existing.ids.push(a.id); existing.count += 1; existing.scan_id = Math.max(existing.scan_id, a.scan_id); }
      else groups.set(key, { ...a, key, ids: [a.id], count: 1 });
    }
    return [...groups.values()].sort((a, b) => b.scan_id - a.scan_id);
  }, [shown, grouped]);
  const pageSize = 25;
  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const visible = rows.slice((Math.min(page, pages) - 1) * pageSize, Math.min(page, pages) * pageSize);
  const pageIds = visible.flatMap(row => row.ids);
  const allPageSelected = pageIds.length > 0 && pageIds.every(id => selected.includes(id));
  const activeIds = shown.filter(a => !a.acknowledged).map(a => a.id);
  const info = alerts.filter(a => a.severity !== "warning" && !a.acknowledged).length;
  const warnings = alerts.filter(a => a.severity === "warning" && !a.acknowledged).length;
  const registered = data?.stats.registered ?? 0;
  const online = data?.stats.responding_last_scan ?? 0;
  const offline = data?.stats.not_responding_last_scan ?? 0;
  const percent = registered ? Math.round(online / registered * 100) : 0;
  const kinds = Object.entries(names).map(([k, n]) => ({ key: k, name: n, count: alerts.filter(a => a.kind === k && !a.acknowledged).length }));
  return <main className="max-w-7xl mx-auto p-5 md:p-7 space-y-6">
    <nav className="flex flex-wrap gap-4 text-blue-700 underline"><Link to="/">Главная</Link><Link to="/scanner">Сканирование</Link><Link to="/scanner/devices">Устройства</Link><Link to="/scanner/history">История</Link></nav>
    <header className="flex flex-wrap justify-between gap-3 items-center"><div><h1 className="text-3xl font-bold">Центр мониторинга 4.1</h1><p className="text-slate-500">Автообновление каждые 30 секунд · уведомления внутри приложения</p></div><button className={button} onClick={() => void refresh()} disabled={busy}>Обновить</button></header>
    {error && <p role="alert" className="border border-red-300 rounded p-3 text-red-700">{error}</p>}
    {notice && <p role="status" className="text-green-700">{notice}</p>}
    {!data ? <p>Загрузка…</p> : <>
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[["В реестре", registered], ["Ответили", online], ["Нет ответа", offline], ["Неподтверждённые", data.stats.unacknowledged]].map(([label, value]) =>
          <div key={label} className="border rounded-xl p-4 bg-white"><p className="text-sm text-slate-500">{label}</p><p className="text-3xl font-bold mt-1">{value}</p></div>)}
      </section>
      <p className="text-sm text-slate-600">Последнее сканирование: {data.stats.last_scan ? `${formatServerDate(data.stats.last_scan.scanned_at)} · ${data.stats.last_scan.subnet}` : "нет данных"}</p>
      <section className="grid lg:grid-cols-2 gap-4">
        <div className="border rounded-xl p-5 space-y-4"><h2 className="text-lg font-semibold">Доступность по последнему сканированию</h2><div className="flex items-center justify-between"><span>Ответили на ping</span><strong>{percent}%</strong></div>
          <div className="h-5 rounded-full bg-slate-200 overflow-hidden" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label="Доля ответивших"><div className="h-full bg-emerald-600" style={{ width: `${percent}%` }} /></div>
          <p className="text-sm text-slate-500">{online} ответили · {offline} без ответа. Отсутствие ответа не доказывает отключение.</p>
          <div className="flex gap-4 text-sm"><span className="text-amber-700">● Внимание: {warnings}</span><span className="text-blue-700">● Информация: {info}</span></div>
        </div>
        <div className="border rounded-xl p-5 space-y-3"><h2 className="text-lg font-semibold">Неподтверждённые по типам</h2>{kinds.map(k => <div key={k.key} className="grid grid-cols-[minmax(125px,1fr)_2fr_35px] gap-2 items-center text-sm"><span>{k.name}</span><div className="bg-slate-100 rounded h-3 overflow-hidden"><div className="h-full bg-blue-600" style={{ width: `${data.stats.unacknowledged ? k.count / data.stats.unacknowledged * 100 : 0}%` }}/></div><strong className="text-right">{k.count}</strong></div>)}</div>
      </section>
      <section className="border rounded-xl p-4"><button className="font-semibold flex justify-between w-full" aria-expanded={showRules} onClick={() => setShowRules(!showRules)}>Правила оповещений {dirty ? "· есть несохранённые изменения" : ""}<span>{showRules ? "Скрыть ▲" : "Настроить ▼"}</span></button>
        {showRules && rules && <div className="space-y-4 mt-4"><div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">{(["new_ip", "mac_changed", "hostname_changed", "detected_again", "missed_ping"] as const).map(k => <label key={k} className="flex gap-2 items-center"><input type="checkbox" checked={rules[k]} onChange={e => { setRules({ ...rules, [k]: e.target.checked }); setDirty(true); }}/>{names[k]}</label>)}</div>
          <label className="flex flex-wrap gap-3 items-center">Сканирований подряд без ответа <input type="number" min={1} max={10} className="border rounded w-20 p-2" value={rules.missed_scans} onChange={e => { setRules({ ...rules, missed_scans: Number(e.target.value) }); setDirty(true); }}/></label>
          <button className="bg-blue-700 text-white rounded px-4 py-2 disabled:opacity-40" disabled={busy || !Number.isInteger(rules.missed_scans) || rules.missed_scans < 1 || rules.missed_scans > 10} onClick={() => void saveRules()}>Сохранить правила</button></div>}
      </section>
      <section className="space-y-3"><div className="flex flex-wrap justify-between gap-3 items-center"><h2 className="text-xl font-semibold">Журнал уведомлений ({shown.length} событий, {rows.length} строк)</h2><label className="flex gap-2 items-center text-sm"><input type="checkbox" checked={grouped} onChange={e => setGrouped(e.target.checked)}/> Группировать по IP и типу</label></div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-2"><input aria-label="Поиск уведомлений" placeholder="IP, событие, номер скана" value={query} onChange={e => setQuery(e.target.value)} className="border rounded p-2"/>
          <select aria-label="Статус" className="border rounded p-2" value={filter} onChange={e => setFilter(e.target.value)}><option value="active">Неподтверждённые</option><option value="ack">Подтверждённые</option><option value="all">Все</option></select>
          <select aria-label="Важность" className="border rounded p-2" value={severity} onChange={e => setSeverity(e.target.value)}><option value="all">Любая важность</option><option value="warning">Внимание</option><option value="info">Информация</option></select>
          <select aria-label="Тип" className="border rounded p-2" value={kind} onChange={e => setKind(e.target.value)}><option value="all">Все типы</option>{Object.entries(names).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></div>
        <div className="flex flex-wrap gap-2 items-center"><button className={button} disabled={busy || !selected.length} onClick={() => void changeAck(selected, true)}>Подтвердить выбранные ({selected.length})</button>
          <button className={button} disabled={busy || !selected.length} onClick={() => void changeAck(selected, false)}>Вернуть выбранные</button>
          <button className={button} disabled={busy || !activeIds.length} onClick={() => { if (window.confirm(`Подтвердить ${activeIds.length} событий по текущим фильтрам?`)) void changeAck(activeIds.slice(0, 500), true); }}>Подтвердить все по фильтру ({activeIds.length})</button></div>
        <div className="border rounded-xl overflow-x-auto"><table className="w-full text-sm text-left"><thead className="bg-slate-100"><tr><th className="p-3"><input aria-label="Выбрать страницу" type="checkbox" checked={allPageSelected} onChange={e => setSelected(old => e.target.checked ? [...new Set([...old, ...pageIds])] : old.filter(id => !pageIds.includes(id)))}/></th>{["IP", "Событие", "Количество", "Последний скан", "Важность", "Действие"].map(h => <th key={h} className="p-3">{h}</th>)}</tr></thead><tbody>{visible.map(row => <tr key={row.key} className="border-t"><td className="p-3"><input aria-label={`Выбрать ${row.ip} ${row.kind}`} type="checkbox" checked={row.ids.every(id => selected.includes(id))} onChange={e => setSelected(old => e.target.checked ? [...new Set([...old, ...row.ids])] : old.filter(id => !row.ids.includes(id)))}/></td><td className="p-3 font-mono">{row.ip}</td><td className="p-3">{row.message}</td><td className="p-3">{row.count}</td><td className="p-3">#{row.scan_id}</td><td className="p-3">{row.severity === "warning" ? "Внимание" : "Информация"}</td><td className="p-3"><button className="text-blue-700 underline disabled:opacity-40" disabled={busy} onClick={() => void changeAck(row.ids, !row.acknowledged)}>{row.acknowledged ? "Вернуть" : "Подтвердить"}</button></td></tr>)}</tbody></table>{!rows.length && <p className="p-4 text-slate-500">По выбранным фильтрам событий нет.</p>}</div>
        <div className="flex justify-between items-center"><p className="text-sm text-slate-500">Страница {Math.min(page, pages)} из {pages}</p><div className="flex gap-2"><button className={button} disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}>Назад</button><button className={button} disabled={page >= pages} onClick={() => setPage(p => Math.min(pages, p + 1))}>Далее</button></div></div>
      </section><p className="text-sm text-slate-500">{data.notice}</p>
    </>}
  </main>;
}
