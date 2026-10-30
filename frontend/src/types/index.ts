// Типы, зеркалят Pydantic-схемы backend.

export type TargetType = "icmp" | "tcp";

export interface Target {
  id: number;
  host: string;
  type: TargetType;
  port: number | null;
  timeout: number;
}

export interface TargetCreate {
  id?: number | null;
  host: string;
  type: TargetType;
  port?: number | null;
  timeout?: number;
}

export interface MonitorResult {
  id: number;           // это target_id, не check_result.id
  host: string;
  type: TargetType;
  ok: boolean;
  ms: number | null;
  error: string | null;
  checked_at: string;   // ISO 8601
  status_changed: boolean;
}

export interface CheckResult {
  id: number;           // check_result.id
  target_id: number;
  ok: boolean;
  ms: number | null;
  error: string | null;
  checked_at: string;
  status_changed: boolean;
}

export type TargetStatus = "UP" | "DOWN" | "UNKNOWN";