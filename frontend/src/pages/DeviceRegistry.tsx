import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { formatServerDate } from "../utils/serverTime";

type Device = {
  id: number; subnet: string; ip: string; label: string; category: string; notes: string;
  mac: string | null; hostname: string | null; first_seen: string; last_seen: string;
  last_scan_at: string; detected_last_scan: boolean;
};
type Observation = { scan_id: number; scanned_at: string; detected: boolean; mac: string | null; hostname: string | null };
type Detail = Device & { history: Observation[] };
type DeviceEvent = { id: number; scan_id: number; ip: string; kind: string; old_value: string | null; new_value: string | null };
type Form = { label: string; category: string; notes: string };

const categories: Record<string, string> = {
  pc: "Компьютер", server: "Сервер", printer: "Принтер", router: "Маршрутизатор",
  phone: "Телефон", iot: "IoT", other: "Другое",
};
const eventNames: Record<string, string> = {
  new_ip: "Новый IP", detected_again: "Снова обнаружен", mac_changed: "Смена MAC", hostname_changed: "Смена имени",
};
const blankForm: Form = { label: "", category: "other", notes: "" };

async function request<T>(url: string, options?: RequestInit, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { ...options, signal, credentials: "same-origin" });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`HTTP ${response.status}${body ? `: ${body.slice(0, 240)}` : ""}`);
  }
  return response.json() as Promise<T>;
}

function Field({ title, value }: { title: string; value: string | number | null | undefined }) {
  return <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 min-w-0">
    <div className="text-xs text-slate-500 mb-1">{title}</div>
    <div className="text-sm font-medium text-slate-900 break-words">{value === null || value === undefined || value === "" ? "—" : value}</div>
  </div>;
}

export function DeviceRegistry() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [events, setEvents] = useState<DeviceEvent[]>([]);
  const [selected, setSelected] = useState<Detail | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState("ip");
  const [error, setError] = useState("");
  const [panelError, setPanelError] = useState("");
  const [loading, setLoading] = useState(true);
  const [panelLoading, setPanelLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<Form>(blankForm);
  const [dirty, setDirty] = useState(false);
  const [activeTab, setActiveTab] = useState<"details" | "history">("details");
  const [page, setPage] = useState(1);
  const panelRef = useRef<HTMLElement | null>(null);
  const lastTrigger = useRef<HTMLElement | null>(null);
  const requestSeq = useRef(0);
  const panelAbort = useRef<AbortController | null>(null);
  const PAGE_SIZE = 50;

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [items, changes] = await Promise.all([
        request<Device[]>("/api/scanner/devices"),
        request<DeviceEvent[]>("/api/scanner/events?limit=100"),
      ]);
      setDevices(items);
      setEvents(changes);
      setError("");
    } catch (e) {
      setError(`Не удалось обновить реестр: ${String(e)}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { setPage(1); }, [query, category, status, sort]);

  const filtered = useMemo(() => {
    const q = query.trim().toLocaleLowerCase("ru-RU");
    const result = devices.filter(d =>
      (category === "all" || d.category === category) &&
      (status === "all" || (status === "online" ? d.detected_last_scan : !d.detected_last_scan)) &&
      [d.ip, d.subnet, d.label, d.hostname, d.mac, d.notes].some(v => (v ?? "").toLocaleLowerCase("ru-RU").includes(q))
    );
    result.sort((a, b) => {
      if (sort === "recent") return (b.last_seen || "").localeCompare(a.last_seen || "");
      if (sort === "name") return (a.label || a.hostname || a.ip).localeCompare(b.label || b.hostname || b.ip, "ru");
      const ai = a.ip.split(".").map(Number), bi = b.ip.split(".").map(Number);
      for (let i = 0; i < Math.min(ai.length, bi.length); i++) if (ai[i] !== bi[i]) return ai[i] - bi[i];
      return a.ip.localeCompare(b.ip);
    });
    return result;
  }, [devices, query, category, status, sort]);
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const visible = filtered.slice((Math.min(page, totalPages) - 1) * PAGE_SIZE, Math.min(page, totalPages) * PAGE_SIZE);
  const online = devices.filter(d => d.detected_last_scan).length;

  const closePanel = useCallback(() => {
    if (dirty && !window.confirm("Есть несохранённые изменения. Закрыть карточку без сохранения?")) return;
    panelAbort.current?.abort();
    requestSeq.current += 1;
    setSelected(null); setSelectedId(null); setPanelError(""); setDirty(false); setPanelLoading(false);
    requestAnimationFrame(() => lastTrigger.current?.focus());
  }, [dirty]);

  useEffect(() => {
    if (selectedId === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); closePanel(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedId, closePanel]);

  const open = useCallback(async (id: number, trigger?: HTMLElement) => {
    if (selectedId !== id && dirty && !window.confirm("Есть несохранённые изменения. Перейти к другой карточке?")) return;
    if (trigger) lastTrigger.current = trigger;
    panelAbort.current?.abort();
    const controller = new AbortController();
    panelAbort.current = controller;
    const seq = ++requestSeq.current;
    setSelectedId(id); setSelected(null); setPanelError(""); setPanelLoading(true);
    setDirty(false); setActiveTab("details");
    try {
      const detail = await request<Detail>(`/api/scanner/devices/${id}`, undefined, controller.signal);
      if (seq !== requestSeq.current) return;
      setSelected(detail);
      setForm({ label: detail.label ?? "", category: detail.category ?? "other", notes: detail.notes ?? "" });
    } catch (e) {
      if (seq !== requestSeq.current || controller.signal.aborted) return;
      setPanelError(`Не удалось загрузить карточку: ${String(e)}`);
    } finally {
      if (seq === requestSeq.current) setPanelLoading(false);
    }
  }, [dirty, selectedId]);

  useEffect(() => {
    if (selectedId !== null) requestAnimationFrame(() => panelRef.current?.focus());
  }, [selectedId]);

  async function save() {
    if (!selected || saving) return;
    setSaving(true); setPanelError("");
    try {
      await request<unknown>(`/api/scanner/devices/${selected.id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form),
      });
      setDirty(false);
      const updated = await request<Detail>(`/api/scanner/devices/${selected.id}`);
      setSelected(updated);
      setForm({ label: updated.label ?? "", category: updated.category ?? "other", notes: updated.notes ?? "" });
      await refresh();
    } catch (e) { setPanelError(`Не удалось сохранить: ${String(e)}`); }
    finally { setSaving(false); }
  }

  function updateForm(next: Form) { setForm(next); setDirty(true); }

  return <main className="max-w-7xl mx-auto p-4 md:p-6 space-y-5">
    <nav className="flex flex-wrap gap-5 text-blue-700 underline text-sm">
      <Link to="/">Главная</Link><Link to="/scanner">Сканер</Link><Link to="/scanner/history">История</Link>
    </nav>
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div><h1 className="text-3xl font-bold text-slate-900">Реестр устройств</h1>
        <p className="text-slate-600 mt-1">Учёт устройств по подсети и IP. Нажмите «Карточка», чтобы открыть подробности справа.</p></div>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={() => void refresh()} disabled={loading} className="border rounded-lg px-4 py-2 bg-white hover:bg-slate-50 disabled:opacity-50">{loading ? "Обновление…" : "Обновить"}</button>
        <a href="/api/scanner/devices/export" className="rounded-lg bg-blue-700 hover:bg-blue-800 text-white px-4 py-2">Экспорт CSV</a>
      </div>
    </header>
    {error && <p role="alert" className="border border-red-300 bg-red-50 rounded-lg p-3 text-red-700">{error}</p>}
    <section className="grid grid-cols-1 sm:grid-cols-3 gap-3" aria-label="Статистика реестра">
      <div className="border rounded-xl p-4 bg-white"><div className="text-sm text-slate-600">Известных IP</div><div className="text-2xl font-bold mt-1">{devices.length}</div></div>
      <div className="border rounded-xl p-4 bg-white"><div className="text-sm text-slate-600">Ответили в последнем скане</div><div className="text-2xl font-bold text-emerald-700 mt-1">{online}</div></div>
      <div className="border rounded-xl p-4 bg-white"><div className="text-sm text-slate-600">Последние события</div><div className="text-2xl font-bold mt-1">{events.length}</div></div>
    </section>
    <section className="space-y-3" aria-label="Список устройств">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <label className="text-sm font-medium">Поиск<input value={query} onChange={e => setQuery(e.target.value)} placeholder="IP, имя, MAC, заметки" className="mt-1 block w-full border rounded-lg p-2 font-normal" /></label>
        <label className="text-sm font-medium">Категория<select value={category} onChange={e => setCategory(e.target.value)} className="mt-1 block w-full border rounded-lg p-2 font-normal"><option value="all">Все категории</option>{Object.entries(categories).map(([k,v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label className="text-sm font-medium">Состояние<select value={status} onChange={e => setStatus(e.target.value)} className="mt-1 block w-full border rounded-lg p-2 font-normal"><option value="all">Все</option><option value="online">Обнаружены</option><option value="offline">Нет ответа</option></select></label>
        <label className="text-sm font-medium">Сортировка<select value={sort} onChange={e => setSort(e.target.value)} className="mt-1 block w-full border rounded-lg p-2 font-normal"><option value="ip">По IP</option><option value="recent">Последний ответ</option><option value="name">По названию</option></select></label>
      </div>
      <div className="flex flex-wrap justify-between items-center gap-3 text-sm text-slate-600"><span>{loading ? "Загрузка…" : `Найдено: ${filtered.length}. Показано: ${visible.length}`}</span>
        {(query || category !== "all" || status !== "all") && <button className="text-blue-700 underline" onClick={() => { setQuery(""); setCategory("all"); setStatus("all"); }}>Сбросить фильтры</button>}</div>
      <div className="overflow-x-auto border rounded-xl bg-white"><table className="w-full text-sm text-left"><thead className="bg-slate-100 text-slate-700"><tr>{["IP", "Название", "Категория", "MAC", "Имя хоста", "Последний ответ", "Последний скан", ""].map(h => <th scope="col" key={h} className="p-3 whitespace-nowrap">{h}</th>)}</tr></thead>
        <tbody>{visible.map(d => <tr key={d.id} className="border-t hover:bg-slate-50"><td className="p-3 font-mono whitespace-nowrap">{d.ip}</td><td className="p-3">{d.label || "—"}</td><td className="p-3">{categories[d.category] ?? d.category}</td><td className="p-3 font-mono whitespace-nowrap">{d.mac ?? "—"}</td><td className="p-3">{d.hostname ?? "—"}</td><td className="p-3 whitespace-nowrap">{formatServerDate(d.last_seen)}</td><td className="p-3"><span className={d.detected_last_scan ? "text-emerald-700 font-medium" : "text-slate-500"}>{d.detected_last_scan ? "Обнаружен" : "Нет ответа"}</span></td><td className="p-3"><button type="button" onClick={e => void open(d.id, e.currentTarget)} className="text-blue-700 underline whitespace-nowrap" aria-label={`Открыть карточку ${d.ip}`}>Карточка</button></td></tr>)}</tbody>
      </table></div>
      {!loading && filtered.length === 0 && <p className="text-center text-slate-500 p-5">Устройства не найдены.</p>}
      {totalPages > 1 && <div className="flex justify-center items-center gap-4 text-sm"><button className="border rounded px-3 py-2 disabled:opacity-40" disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}>Назад</button><span>Страница {Math.min(page, totalPages)} из {totalPages}</span><button className="border rounded px-3 py-2 disabled:opacity-40" disabled={page >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))}>Вперёд</button></div>}
    </section>
    <section className="space-y-2"><h2 className="text-xl font-semibold">Последние события</h2><p className="text-sm text-slate-600">События обновляются после сканирования. Push-уведомления пока не поддерживаются.</p>
      <div className="border rounded-xl max-h-72 overflow-auto bg-white"><table className="w-full text-sm text-left"><thead className="bg-slate-100"><tr><th className="p-3">Скан</th><th className="p-3">IP</th><th className="p-3">Событие</th><th className="p-3">Изменение</th></tr></thead><tbody>{events.map(e => <tr key={e.id} className="border-t"><td className="p-3">#{e.scan_id}</td><td className="p-3 font-mono">{e.ip}</td><td className="p-3">{eventNames[e.kind] ?? e.kind}</td><td className="p-3">{e.old_value ?? "—"} → {e.new_value ?? "—"}</td></tr>)}</tbody></table>{events.length === 0 && <p className="p-4 text-slate-500">Событий пока нет.</p>}</div>
    </section>
    {selectedId !== null && <div className="fixed inset-0 z-50 flex justify-end" role="presentation">
      <button type="button" aria-label="Закрыть карточку" onClick={closePanel} className="absolute inset-0 bg-slate-900/40 cursor-default" />
      <aside ref={panelRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="device-panel-title" className="relative bg-white h-full w-full sm:max-w-xl shadow-2xl overflow-y-auto outline-none flex flex-col">
        <div className="sticky top-0 bg-white border-b z-10 p-4 flex items-start justify-between gap-3"><div><h2 id="device-panel-title" className="text-xl font-bold">Карточка устройства</h2><div className="text-sm font-mono text-slate-600 mt-1">{selected?.ip ?? devices.find(d => d.id === selectedId)?.ip ?? `#${selectedId}`}</div></div><button type="button" onClick={closePanel} className="border rounded-lg px-3 py-2 hover:bg-slate-100" aria-label="Закрыть">✕</button></div>
        <div className="p-4 space-y-5 flex-1">
          {panelLoading && <p role="status">Загрузка карточки…</p>}
          {panelError && <p role="alert" className="border border-red-300 bg-red-50 text-red-700 rounded-lg p-3">{panelError}</p>}
          {!panelLoading && !selected && <button type="button" className="text-blue-700 underline" onClick={() => void open(selectedId)}>Повторить загрузку</button>}
          {selected && <>
            <div className="flex gap-2 border-b"><button className={`px-3 py-2 ${activeTab === "details" ? "border-b-2 border-blue-700 font-semibold" : "text-slate-500"}`} onClick={() => setActiveTab("details")}>Информация</button><button className={`px-3 py-2 ${activeTab === "history" ? "border-b-2 border-blue-700 font-semibold" : "text-slate-500"}`} onClick={() => setActiveTab("history")}>История ({selected.history?.length ?? 0})</button></div>
            {activeTab === "details" ? <div className="space-y-4">
              <div className="grid grid-cols-2 gap-2"><Field title="IP-адрес" value={selected.ip} /><Field title="Подсеть" value={selected.subnet} /><Field title="MAC" value={selected.mac} /><Field title="Имя хоста" value={selected.hostname} /><Field title="Первое обнаружение" value={formatServerDate(selected.first_seen)} /><Field title="Последний ответ" value={formatServerDate(selected.last_seen)} /></div>
              <div className="rounded-lg border p-3"><span className={selected.detected_last_scan ? "text-emerald-700 font-semibold" : "text-slate-600 font-semibold"}>{selected.detected_last_scan ? "● Обнаружен в последнем скане" : "○ Нет ответа в последнем скане"}</span></div>
              <label className="block text-sm font-medium">Название<input maxLength={100} value={form.label} onChange={e => updateForm({ ...form, label: e.target.value })} className="mt-1 block w-full border rounded-lg p-2 font-normal" /></label>
              <label className="block text-sm font-medium">Категория<select value={form.category} onChange={e => updateForm({ ...form, category: e.target.value })} className="mt-1 block w-full border rounded-lg p-2 font-normal">{Object.entries(categories).map(([k,v]) => <option key={k} value={k}>{v}</option>)}</select></label>
              <label className="block text-sm font-medium">Заметки<textarea rows={5} maxLength={2000} value={form.notes} onChange={e => updateForm({ ...form, notes: e.target.value })} className="mt-1 block w-full border rounded-lg p-2 font-normal" /></label>
              <button type="button" disabled={saving || !dirty} onClick={() => void save()} className="w-full rounded-lg bg-blue-700 text-white py-3 disabled:opacity-50 hover:bg-blue-800">{saving ? "Сохранение…" : dirty ? "Сохранить изменения" : "Изменений нет"}</button>
            </div> : <div className="space-y-2"><p className="text-sm text-slate-500">Последние наблюдения устройства</p><div className="overflow-x-auto"><table className="w-full text-sm"><thead className="bg-slate-100"><tr><th className="p-2 text-left">Скан</th><th className="p-2 text-left">Дата</th><th className="p-2 text-left">Ответ</th><th className="p-2 text-left">MAC</th></tr></thead><tbody>{(selected.history ?? []).map(h => <tr key={h.scan_id} className="border-t"><td className="p-2">#{h.scan_id}</td><td className="p-2 whitespace-nowrap">{formatServerDate(h.scanned_at)}</td><td className="p-2">{h.detected ? "Да" : "Нет"}</td><td className="p-2 font-mono">{h.mac ?? "—"}</td></tr>)}</tbody></table></div>{!selected.history?.length && <p className="text-slate-500">История пока пуста.</p>}</div>}
          </>}
        </div>
      </aside>
    </div>}
  </main>;
}
