import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import StatusBadge from "./StatusBadge.jsx";

function RowHoverCard({ row }) {
  const rows = [
    ["MR #", row.work_order_id],
    ["Site", row.department],
    ["Asset", row.location],
    ["Assigned", row.assigned_to],
    ["Supplier", row.supplier],
    ["PO", row.po_number],
    ["Purchase type", row.work_type],
    ["Created", (row.created_date || "").slice(0, 10)],
    ["Due", (row.due_date || "").slice(0, 10)],
    ["PO / RFQ date", (row.scheduled_date || "").slice(0, 10)],
    ["Age (days)", row.aging_days],
    ["Overdue (days)", row.days_overdue],
    ["Delay type", row.delay_kind],
    ["Delay source", row.delay_source],
  ];
  const just = row.delay_justification || row.delay_reason || row.issue;
  return createPortal(
    <div
      role="tooltip"
      className="fixed z-[90] pointer-events-none w-[340px] max-w-[90vw] rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-ink-900 shadow-2xl p-3 text-left"
      style={{ top: row._hoverY, left: row._hoverX }}
    >
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <span className="font-mono text-xs font-bold">{row.work_order_id}</span>
        <StatusBadge value={row.status} />
      </div>
      <div className="text-sm font-medium mb-2 line-clamp-3">{row.description || "—"}</div>
      <dl className="grid grid-cols-[86px_1fr] gap-x-2 gap-y-0.5 text-[11px]">
        {rows
          .filter(([, v]) => v !== undefined && v !== null && String(v).trim() !== "")
          .map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-slate-400">{k}</dt>
              <dd className="text-slate-700 dark:text-slate-200 truncate">{String(v).slice(0, 60)}</dd>
            </div>
          ))}
      </dl>
      {just ? (
        <div className="mt-2 rounded-lg bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 px-2 py-1.5 text-[11px] text-amber-800 dark:text-amber-200">
          <span className="font-semibold">Justification: </span>
          {just}
        </div>
      ) : null}
      {row.remarks ? (
        <div className="mt-1.5 text-[11px] text-slate-500 line-clamp-2">
          <span className="font-semibold">Remarks: </span>
          {row.remarks}
        </div>
      ) : null}
      <div className="mt-2 text-[10px] text-slate-400">Click the row to open the material request</div>
    </div>,
    document.body
  );
}

export default function OpsTable({ title, subtitle, rows, columns, empty, onRow, viewAll, seen, onSeen, claim, onClaim }) {
  const nav = useNavigate();
  const [hover, setHover] = useState(null);
  const timer = useRef(null);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const baseCols = columns || [
    ["work_order_id", "MR #"],
    ["description", "Material"],
    ["department", "Site"],
    ["assigned_to", "Assigned"],
    ["status", "Status"],
    ["supplier", "Supplier"],
    ["po_number", "PO"],
    ["due_date", "Due"],
    ["aging_days", "Age"],
  ];
  const extra = [];
  if (claim) extra.push(["_claim", "Claim"]);
  if (seen) extra.push(["_seen", "Seen"]);
  const cols = extra.length ? [...baseCols, ...extra] : baseCols;

  function open(r) {
    if (onRow) return onRow(r);
    nav(`/work-orders/${encodeURIComponent(r.record_id || r.work_order_id)}`);
  }

  function hoverRow(r, e) {
    window.clearTimeout(timer.current);
    const target = r;
    timer.current = window.setTimeout(() => {
      // place near the cursor but clamp to the viewport
      const x = Math.min((e.clientX || 200) + 16, window.innerWidth - 360);
      const y = Math.min((e.clientY || 200) + 12, window.innerHeight - 300);
      setHover({ ...target, _hoverX: Math.max(8, x), _hoverY: Math.max(8, y) });
    }, 320);
  }
  function leaveRow() {
    window.clearTimeout(timer.current);
    setHover(null);
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
              <tr
                key={r.record_id || `${r.work_order_id}-${r._row}`}
                onClick={() => open(r)}
                onMouseEnter={(e) => hoverRow(r, e)}
                onMouseMove={(e) => {
                  if (hover && hover.record_id === (r.record_id || r.work_order_id)) {
                    const x = Math.min((e.clientX || 200) + 16, window.innerWidth - 360);
                    const y = Math.min((e.clientY || 200) + 12, window.innerHeight - 300);
                    setHover((prev) => (prev ? { ...prev, _hoverX: Math.max(8, x), _hoverY: Math.max(8, y) } : prev));
                  }
                }}
                onMouseLeave={leaveRow}
                className="cursor-pointer hover:bg-slate-50 dark:hover:bg-white/5 transition-colors"
              >
                {cols.map(([k]) => (
                  <td key={k} className={k === "description" || k === "remarks" ? "max-w-[280px] truncate" : ""}>
                    {k === "status" || k === "priority" || k === "issue" ? (
                      k === "status" ? (
                        <span
                          title={`Show all ${r[k] || ""} material requests`}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (r[k]) nav(`/work-orders?status=${encodeURIComponent(r[k])}`);
                          }}
                          className="inline-block hover:ring-2 hover:ring-brand-500/50 rounded-full transition-shadow"
                        >
                          <StatusBadge value={r[k]} />
                        </span>
                      ) : (
                        <StatusBadge value={r[k]} />
                      )
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
                    ) : k === "_claim" ? (
                      <div className="no-print" onClick={(e) => e.stopPropagation()}>
                        <button type="button" className="btn-outline !py-0.5 !px-2 text-[11px]" onClick={() => onClaim?.(r)}>
                          Claim
                        </button>
                      </div>
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
      {hover && <RowHoverCard row={hover} />}
    </div>
  );
}
