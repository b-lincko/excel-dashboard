import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Download,
  FileSpreadsheet,
  PlusCircle,
  Printer,
} from "lucide-react";
import { api, qs } from "../lib/api.js";
import { goSearch, useLiveReload } from "../lib/live.js";
import KPICard from "../components/KPICard.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

const OTHER = [
  ["monthly", "Monthly report"],
  ["yearly", "Yearly report"],
  ["open", "Open material requests"],
  ["overdue", "Overdue material requests"],
  ["closed", "Closed material requests"],
  ["delay", "Delay / issue report"],
  ["department", "Site report"],
  ["technician", "Assignee report"],
];

function todayIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function shiftIso(iso, days) {
  const [y, m, d] = (iso || todayIso()).split("-").map(Number);
  const next = new Date(y, m - 1, d + days);
  return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}-${String(next.getDate()).padStart(2, "0")}`;
}

function Section({ title, count, shown, children, onViewAll }) {
  return (
    <div className="card overflow-hidden print-break">
      <div className="px-4 py-3 flex items-center justify-between gap-3 border-b border-slate-100 dark:border-white/5">
        <div>
          <div className="font-semibold">{title}</div>
          <div className="text-xs text-slate-500">
            {count} {count === 1 ? "request" : "requests"}
            {count > shown ? ` · showing ${shown}` : ""}
          </div>
        </div>
        {onViewAll && (
          <button type="button" className="btn-outline !py-1 text-xs no-print" onClick={onViewAll}>
            View all
          </button>
        )}
      </div>
      {children}
    </div>
  );
}

function Rows({ rows, empty, extra, onOpen }) {
  if (!rows?.length) {
    return <div className="p-6 text-center text-sm text-slate-500">{empty}</div>;
  }
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th>IM WO #</th>
            <th>Site</th>
            <th>Material</th>
            <th>{extra || "Due"}</th>
            <th>Assigned</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.record_id || r.work_order_id} onClick={() => onOpen(r)}>
              <td className="font-mono text-xs font-semibold">{r.work_order_id}</td>
              <td>{r.department || "—"}</td>
              <td className="max-w-[280px] truncate">{r.description || "—"}</td>
              <td>{(extra === "Opened" ? r.created_date : r.due_date) || "—"}</td>
              <td>{r.assigned_to || "—"}</td>
              <td>
                <StatusBadge value={r.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Reports() {
  const nav = useNavigate();
  const tick = useLiveReload();
  const [tab, setTab] = useState("daily");
  const [asOf, setAsOf] = useState(todayIso);
  const [period, setPeriod] = useState("this_year");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (tab === "more") {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    api
      .get(`/api/reports/${tab}${qs({ fmt: "json", as_of: asOf })}`)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) {
          setData(null);
          setError(e.message);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tab, asOf, tick]);

  async function download(kind, fmt, extra = {}) {
    setBusy(`${kind}-${fmt}`);
    setError("");
    try {
      const ext = fmt === "xlsx" ? "xlsx" : fmt;
      await api.download(`/api/reports/${kind}${qs({ fmt, ...extra })}`, `${kind}_report.${ext}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }

  const k = data?.kpis || {};
  const lists = data?.lists || {};
  const totals = data?.totals || {};
  const step = tab === "weekly" ? 7 : 1;
  const openWo = (r) => nav(`/work-orders/${encodeURIComponent(r.record_id || r.work_order_id)}`);

  return (
    <div className="space-y-5 briefing">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Reports</h1>
          <p className="text-sm text-slate-500">
            Pick a day or an ISO week. Daily covers that calendar day only; weekly covers Monday–Sunday of the chosen date.
          </p>
        </div>
        <div className="tab-bar no-print">
          {[
            ["daily", "Daily"],
            ["weekly", "Weekly"],
            ["more", "More"],
          ].map(([id, label]) => (
            <button key={id} type="button" className={`tab-btn ${tab === id ? "is-on" : ""}`} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="text-sm text-rose-600 no-print">{error}</div>}

      {tab !== "more" && (
        <>
          <div className="card p-4 flex flex-wrap items-end justify-between gap-3 no-print">
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <label className="lbl">{tab === "weekly" ? "Any date in the week" : "Report date"}</label>
                <div className="flex items-center gap-1">
                  <button type="button" className="btn-outline !px-2" onClick={() => setAsOf(shiftIso(asOf, -step))} title="Previous">
                    <ChevronLeft size={16} />
                  </button>
                  <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value || todayIso())} className="w-[11.5rem]" />
                  <button type="button" className="btn-outline !px-2" onClick={() => setAsOf(shiftIso(asOf, step))} title="Next">
                    <ChevronRight size={16} />
                  </button>
                </div>
              </div>
              <button type="button" className="btn-outline" onClick={() => setAsOf(todayIso())}>
                <CalendarDays size={14} /> {tab === "weekly" ? "This week" : "Today"}
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-outline" disabled={!!busy} onClick={() => download(tab, "pdf", { as_of: asOf })}>
                <Download size={14} /> PDF
              </button>
              <button type="button" className="btn-outline" disabled={!!busy} onClick={() => download(tab, "xlsx", { as_of: asOf })}>
                <FileSpreadsheet size={14} /> Excel
              </button>
              <button type="button" className="btn-outline" disabled={!!busy} onClick={() => download(tab, "csv", { as_of: asOf })}>
                CSV
              </button>
              <button type="button" className="btn-primary" onClick={() => window.print()}>
                <Printer size={14} /> Print
              </button>
            </div>
          </div>

          <div className="print-only text-xs text-slate-500">
            Linkco MR · {data?.title || (tab === "weekly" ? "Weekly report" : "Daily report")} · {data?.label || asOf} · printed {new Date().toLocaleString()}
          </div>

          <div>
            <h2 className="text-lg font-semibold tracking-tight">{data?.title || (tab === "weekly" ? "Weekly report" : "Daily report")}</h2>
            <p className="text-sm text-slate-500">
              {data?.label || asOf}
              {loading ? " · updating…" : ""}
            </p>
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <KPICard label="New MRs" value={k.created} icon={PlusCircle} accent="sky" onClick={() => goSearch(nav, { date_from: data?.start, date_to: data?.end })} />
            <KPICard label="Closed" value={k.closed} icon={CheckCircle2} accent="emerald" onClick={() => goSearch(nav, { flag: "closed", date_from: data?.start, date_to: data?.end })} />
            <KPICard label="Overdue" value={k.overdue} icon={AlertTriangle} accent="rose" onClick={() => goSearch(nav, { flag: "overdue" })} />
            <KPICard label="Due this period" value={k.due} icon={Clock} accent="amber" onClick={() => goSearch(nav, { date_from: data?.start, date_to: data?.end, flag: "outstanding" })} />
          </div>

          {(data?.by_site || []).length > 0 && (
            <div className="flex flex-wrap gap-2">
              {data.by_site.map((s) => (
                <div key={s.name} className="stat-tile text-xs">
                  <span className="font-semibold">{s.name}</span>
                  <span className="text-slate-500"> · {s.value}</span>
                </div>
              ))}
            </div>
          )}

          {tab === "weekly" && (data?.days || []).length > 0 && (
            <div className="grid grid-cols-7 gap-2 print-break">
              {data.days.map((d) => (
                <button
                  key={d.date}
                  type="button"
                  className={`card p-3 text-center ${d.date === asOf ? "ring-2 ring-brand-500" : ""}`}
                  onClick={() => {
                    setTab("daily");
                    setAsOf(d.date);
                  }}
                >
                  <div className="text-[11px] uppercase tracking-wider text-slate-500">{d.name}</div>
                  <div className="mt-1 text-lg font-bold tabular-nums">{d.created}</div>
                  <div className="text-[11px] text-slate-500">{d.closed} closed</div>
                  <div className="text-[11px] text-rose-600">{d.overdue} overdue</div>
                </button>
              ))}
            </div>
          )}

          {loading && !data ? (
            <div className="grid gap-3">
              <div className="skel h-40" />
              <div className="skel h-40" />
            </div>
          ) : (
            <div className="space-y-4">
              <Section
                title="New material requests"
                count={totals.created || 0}
                shown={(lists.created || []).length}
                onViewAll={() => goSearch(nav, { date_from: data?.start, date_to: data?.end })}
              >
                <Rows rows={lists.created} empty="No new material requests in this period." extra="Opened" onOpen={openWo} />
              </Section>
              <Section
                title="Closed / completed"
                count={totals.closed || 0}
                shown={(lists.closed || []).length}
                onViewAll={() => goSearch(nav, { flag: "closed", date_from: data?.start, date_to: data?.end })}
              >
                <Rows rows={lists.closed} empty="Nothing closed in this period." extra="Opened" onOpen={openWo} />
              </Section>
              <Section
                title="Still overdue"
                count={totals.overdue || 0}
                shown={(lists.overdue || []).length}
                onViewAll={() => goSearch(nav, { flag: "overdue" })}
              >
                <Rows rows={lists.overdue} empty="No overdue requests at the end of this period." extra="Due" onOpen={openWo} />
              </Section>
            </div>
          )}
        </>
      )}

      {tab === "more" && (
        <div className="space-y-4 no-print">
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
          <div className="grid md:grid-cols-2 gap-3">
            {OTHER.map(([id, label]) => (
              <div key={id} className="card p-4 flex items-center justify-between gap-3">
                <div>
                  <div className="font-semibold">{label}</div>
                  <div className="text-xs text-slate-500">KPI summary and matching material requests</div>
                </div>
                <div className="flex gap-1">
                  {["xlsx", "csv", "pdf"].map((fmt) => (
                    <button
                      key={fmt}
                      type="button"
                      className="btn-outline !px-2 !py-1 text-xs uppercase"
                      disabled={busy === `${id}-${fmt}`}
                      onClick={() => download(id, fmt, { period })}
                    >
                      <Download size={12} /> {fmt}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
