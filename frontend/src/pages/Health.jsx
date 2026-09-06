import { useEffect, useState } from "react";
import { api } from "../lib/api.js";
import { useUi } from "../context/UiContext.jsx";
import KPICard from "../components/KPICard.jsx";

const SECTIONS = [
  ["missing_id", "Missing work-order IDs", "Rows with data but a blank IM Work Order #. The normal reader skips these."],
  ["blank_assign", "Blank Assign to (open)", "Open rows with no assignee."],
  ["blank_status", "Blank STATUS", "Rows that have a WO # but no status."],
  ["overwritten_formula", "Formula columns typed over", "Configured formula columns that now hold a typed value instead of a formula."],
  ["missing_formula", "Formula columns empty", "Configured formula columns that are blank."],
  ["duplicate_id", "Duplicate WO # on a sheet", "The same IM Work Order # appears more than once on one worksheet."],
];

export default function Health() {
  const { toast } = useUi();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    api
      .get("/api/ops/health")
      .then(setData)
      .catch((e) => toast(e.message, "error"))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  const c = data?.counts || {};
  const issues = data?.issues || {};

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Excel health</h1>
          <p className="text-sm text-slate-500">
            Raw scan of the live workbook · {data?.scanned_rows ?? "—"} data rows on {data?.sheets ?? "—"} sheets
            {loading ? " · scanning…" : ""}
          </p>
        </div>
        <button className="btn-outline" onClick={load} disabled={loading}>
          {loading ? "Scanning…" : "Scan again"}
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <KPICard label="Missing IDs" value={c.missing_id} accent="rose" />
        <KPICard label="Blank assign" value={c.blank_assign} accent="amber" />
        <KPICard label="Blank status" value={c.blank_status} accent="amber" />
        <KPICard label="Typed-over formulas" value={c.overwritten_formula} accent="rose" />
        <KPICard label="Empty formulas" value={c.missing_formula} accent="sky" />
        <KPICard label="Duplicate WO #" value={c.duplicate_id} accent="rose" />
      </div>

      {SECTIONS.map(([key, title, hint]) => {
        const rows = issues[key] || [];
        const count = c[key] ?? rows.length;
        return (
          <div key={key} className="card overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 dark:border-white/5">
              <div className="font-semibold">
                {title} ({count})
              </div>
              <div className="text-xs text-slate-500 mt-0.5">{hint}</div>
            </div>
            <div className="table-wrap max-h-[280px]">
              <table className="data">
                <thead>
                  <tr>
                    <th>Site</th>
                    <th>Row</th>
                    <th>IM WO #</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={`${r.record_id || r.work_order_id || i}-${i}`} className="!cursor-default">
                      <td>{r.site || r.sheet || "—"}</td>
                      <td className="font-mono text-xs">{r.row || (r.rows || []).join(", ") || "—"}</td>
                      <td className="font-mono text-xs">{r.work_order_id || "—"}</td>
                      <td className="text-sm text-slate-500 truncate max-w-[360px]">
                        {r.column ? `${r.column}${r.value ? ` = ${r.value}` : ""}` : r.status || r.record_id || "—"}
                      </td>
                    </tr>
                  ))}
                  {!rows.length && (
                    <tr className="!cursor-default">
                      <td colSpan={4} className="text-center text-slate-400 py-8">
                        None found in this scan.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
}
