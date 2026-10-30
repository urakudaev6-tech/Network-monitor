import type { TargetStatus } from "../types";

const styles: Record<TargetStatus, string> = {
  UP: "bg-green-100 text-green-800 border-green-300",
  DOWN: "bg-red-100 text-red-800 border-red-300",
  UNKNOWN: "bg-slate-100 text-slate-600 border-slate-300",
};

export function StatusBadge({ status }: { status: TargetStatus }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${styles[status]}`}
    >
      {status}
    </span>
  );
}