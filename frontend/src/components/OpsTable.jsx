import { useNavigate } from "react-router-dom";
import StatusBadge from "./StatusBadge.jsx";

export default function OpsTable({ title, subtitle, rows, columns, empty, onRow, viewAll, seen, onSeen }) {
  const nav = useNavigate();
  const baseCols = columns || [
    ["work_order_id", "IM WO #"],
    ["description", "Material"],
    ["department", "Site"],
    ["assigned_to", "Assigned"],
    ["status", "Status"],
    ["supplier", "Supplier"],
    ["po_number", "PO"],
    ["due_date", "Due"],
    ["aging_days", "Age"],
  ];
  const cols = seen ? [...baseCols, ["_seen", "Seen"]] : baseCols;

  function open(r) {
    if (onRow) return onRow(r);
    nav(`/work-orders/${encodeURIComponent(r.record_id || r.work_order_id)}`);
  }

  return (
    <div className="card overflow-hidden print-break">
      <div className="px-4 py-3 flex items-center justify-between gap-3 border-b border-slate-100 dark:border-white/5">
        <div>
          <div className="font-semibold">{title}</div>
          {subtitle && <div className="text-xs text-slate-500 mt-0.5">{subtitle}</div>}
        </div>
        {viewAll && (
          <button className="btn-ghost text-sm no-print" onClick={viewAll}>
            View all
          </button>
        )}
      </div>
      <div className="table-wrap max-h-[360px]">
        <table className="data">
          <thead>
            <tr>
              {cols.map(([k, l]) => (
                <th key={k}>{l}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(rows || []).map((r) => (
              <tr key={r.record_id || `${r.work_order_id}-${r._row}`} onClick={() => open(r)}>
                {cols.map(([k]) => (
                  <td key={k} className={k === "description" || k === "remarks" ? "max-w-[280px] truncate" : ""}>
                    {k === "status" || k === "priority" || k === "issue" ? (
                      <StatusBadge value={r[k]} />
                    ) : k === "work_order_id" ? (
                      <span className="font-mono text-xs font-semibold">{r[k]}</span>
                    ) : k.endsWith("_date") ? (
                      (r[k] || "").slice(0, 10) || "—"
                    ) : k === "days_overdue" || k === "days_to_eta" ? (
                      r[k] != null ? (
                        <span className={Number(r[k]) < 0 || k === "days_overdue" ? "text-rose-600 font-semibold" : ""}>
                          {r[k]}
                        </span>
                      ) : (
                        "—"
                      )
                    ) : k === "_seen" ? (
                      <div className="flex items-center gap-2 no-print" onClick={(e) => e.stopPropagation()}>
                        <button type="button" className="btn-outline !py-0.5 !px-2 text-[11px]" onClick={() => onSeen?.(r)}>
                          Mark seen
                        </button>
                        <span className="text-[11px] text-slate-500 truncate max-w-[120px]">
                          {(r.seen_by || []).map((s) => s.username).join(", ") || "—"}
                        </span>
                      </div>
                    ) : (
                      r[k] ?? "—"
                    )}
                  </td>
                ))}
              </tr>
            ))}
            {!(rows || []).length && (
              <tr>
                <td colSpan={cols.length} className="text-center text-slate-400 py-8">
                  {empty || "Nothing in this list."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
