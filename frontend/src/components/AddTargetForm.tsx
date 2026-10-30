import { useState } from "react";
import type { TargetCreate, TargetType } from "../types";

interface Props {
  onSubmit: (payload: TargetCreate) => void;
  isSubmitting?: boolean;
  error?: string | null;
}

export function AddTargetForm({ onSubmit, isSubmitting, error }: Props) {
  const [host, setHost] = useState("");
  const [type, setType] = useState<TargetType>("icmp");
  const [port, setPort] = useState("");
  const [timeout, setTimeout] = useState("2");
  const [localError, setLocalError] = useState<string | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setLocalError(null);

    const trimmedHost = host.trim();
    if (!trimmedHost) {
      setLocalError("Хост не может быть пустым");
      return;
    }
    const timeoutNum = Number(timeout);
    if (!Number.isFinite(timeoutNum) || timeoutNum <= 0) {
      setLocalError("Тайм-аут должен быть > 0");
      return;
    }
    const portNum = port.trim() ? Number(port) : null;
    if (type === "tcp" && portNum == null) {
      setLocalError("Для TCP обязателен порт");
      return;
    }
    if (portNum != null && (portNum < 1 || portNum > 65535)) {
      setLocalError("Порт должен быть 1..65535");
      return;
    }

    onSubmit({
      host: trimmedHost,
      type,
      port: portNum,
      timeout: timeoutNum,
    });
    setHost("");
    setPort("");
    setType("icmp");
    setTimeout("2");
  }

  return (
    <form onSubmit={submit} className="bg-white rounded shadow p-4 space-y-3">
      <h2 className="font-semibold">Добавить устройство</h2>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="flex flex-col">
          <span className="text-xs text-slate-600 mb-1">Хост / IP</span>
          <input
            value={host}
            onChange={(e) => setHost(e.target.value)}
            placeholder="8.8.8.8"
            className="border rounded px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </label>

        <label className="flex flex-col">
          <span className="text-xs text-slate-600 mb-1">Тип</span>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as TargetType)}
            className="border rounded px-2 py-1.5"
          >
            <option value="icmp">ICMP (ping)</option>
            <option value="tcp">TCP (порт)</option>
          </select>
        </label>

        <label className="flex flex-col">
          <span className="text-xs text-slate-600 mb-1">
            Порт {type === "icmp" && "(не нужен)"}
          </span>
          <input
            value={port}
            onChange={(e) => setPort(e.target.value)}
            placeholder="443"
            disabled={type === "icmp"}
            className="border rounded px-2 py-1.5 disabled:bg-slate-100"
          />
        </label>

        <label className="flex flex-col">
          <span className="text-xs text-slate-600 mb-1">Тайм-аут, сек</span>
          <input
            value={timeout}
            onChange={(e) => setTimeout(e.target.value)}
            placeholder="2"
            className="border rounded px-2 py-1.5"
          />
        </label>
      </div>

      {(localError || error) && (
        <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">
          {localError ?? error}
        </div>
      )}

      <button
        type="submit"
        disabled={isSubmitting}
        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
      >
        {isSubmitting ? "Добавляю..." : "Добавить"}
      </button>
    </form>
  );
}