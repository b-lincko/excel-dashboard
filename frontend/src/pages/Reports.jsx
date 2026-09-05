import { useState } from "react";
import { Download } from "lucide-react";
import { api, qs } from "../lib/api.js";

const REPORTS = [
  ["daily", "Daily Report"],
  ["weekly", "Weekly Report"],
  ["monthly", "Monthly Report"],
  ["yearly", "Yearly Report"],
  ["open", "Open Work Order Report"],
  ["overdue", "Overdue Work Order Report"],
  ["closed", "Closed Work Order Report"],
  ["delay", "Delay / Issue Report"],
  ["department", "Department Report"],
  ["technician", "Technician Report"],
];

export default function Reports() {
  const [period, setPeriod] = useState("this_year");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function download(kind, fmt) {
    setBusy(`${kind}-${fmt}`);
    setError("");
    try {
      await api.download(`/api/reports/${kind}${qs({ fmt, period })}`, `${kind}_report.${fmt === "xlsx" ? "xlsx" : fmt}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="space-y-5 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Reports</h1>
        <p className="text-sm text-slate-500">Generated from the live Excel dataset. Export Excel, CSV or PDF.</p>
      </div>
      <div className="card p-4 w-64">
        <label className="lbl">Date period</label>
        <select value={period} onChange={(e) => setPeriod(e.target.value)}>
          <option value="">All time</option>
          <option value="today">Today</option>
          <option value="this_week">This week</option>
          <option value="this_month">This month</option>
          <option value="this_quarter">This quarter</option>
          <option value="this_year">This year</option>
          <option value="last_year">Last year</option>
        </select>
      </div>
      {error && <div className="text-sm text-rose-600">{error}</div>}
      <div className="grid md:grid-cols-2 gap-3">
        {REPORTS.map(([id, label]) => (
          <div key={id} className="card p-4 flex items-center justify-between gap-3">
            <div>
              <div className="font-semibold">{label}</div>
              <div className="text-xs text-slate-500">Includes KPI summary and matching work orders</div>
            </div>
            <div className="flex gap-1">
              {["xlsx", "csv", "pdf"].map((fmt) => (
                <button
                  key={fmt}
                  className="btn-outline !px-2 !py-1 text-xs uppercase"
                  disabled={busy === `${id}-${fmt}`}
                  onClick={() => download(id, fmt)}
                >
                  <Download size={12} /> {fmt}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
