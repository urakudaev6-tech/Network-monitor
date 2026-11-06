/** Network Monitor timestamps are stored as UTC. Missing offsets are treated as UTC. */
const MOSCOW_TZ = "Europe/Moscow";

export function parseServerDate(value: string): Date {
  const normalized = value.trim();
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized);
  return new Date(hasTimezone ? normalized : `${normalized}Z`);
}

export function formatServerDate(value: string): string {
  const date = parseServerDate(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("ru-RU", { timeZone: MOSCOW_TZ });
}

export function formatServerTime(value: string): string {
  const date = parseServerDate(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleTimeString("ru-RU", { timeZone: MOSCOW_TZ });
}
