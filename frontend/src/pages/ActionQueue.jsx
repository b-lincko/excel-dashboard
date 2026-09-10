import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Ban, Bell, CalendarClock, ClipboardList, PauseCircle, Printer, Truck, X } from "lucide-react";
import { api, qs } from "../lib/api.js";
import { useApiData, useOptionsCache } from "../lib/apiCache.js";
import { goSearch, useLiveReload } from "../lib/live.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";
import KPICard from "../components/KPICard.jsx";
import OpsTable from "../components/OpsTable.jsx";
import Filters from "../components/Filters.jsx";

const SECTIONS = [
  {
    id: "overdue",
    title: "Overdue",
    hint: "Due date has passed and STATUS is not CLOSED",
    flag: "overdue",
    cols: [
      ["work_order_id", "MR #"],
      ["description", "Material"],
      ["department", "Site"],
      ["assigned_to", "Assigned"],
      ["status", "Status"],
      ["due_date", "Due"],
      ["days_overdue", "Days late"],
      ["priority", "Priority"],
    ],
  },
  {
    id: "ntp",
    title: "UNDER NTP",
    hint: "Waiting on NTP — follow up today",
    flag: "ntp",
    cols: [
      ["work_order_id", "MR #"],
      ["description", "Material"],
      ["assigned_to", "Assigned"],
      ["supplier", "Supplier"],
      ["issue", "Delivery"],
      ["aging_days", "Age (d)"],
      ["remarks", "Remarks"],
    ],
  },
  {
    id: "on_hold",
    title: "ON HOLD",
    hint: "Blocked until released",
    flag: "on_hold",
    cols: [
      ["work_order_id", "MR #"],
      ["description", "Material"],
      ["assigned_to", "Assigned"],
      ["status", "Status"],
      ["aging_days", "Age (d)"],
      ["remarks", "Remarks"],
    ],
  },
  {
    id: "due_soon",
    title: "Due in 1–3 days",
    hint: "Open MRs whose due date is today through 3 days",
    flag: "due_soon",
    cols: [
      ["work_order_id", "MR #"],
      ["description", "Material"],
      ["department", "Site"],
      ["assigned_to", "Assigned"],
      ["status", "Status"],
      ["due_date", "Due"],
      ["days_until_due", "Days left"],
      ["priority", "Priority"],
    ],
  },
  {
    id: "due_this_week",
    title: "Due this week",
    hint: "Still open, due date is today or later this week",
    flag: "due_week",
    cols: [
      ["work_order_id", "MR #"],
      ["description", "Material"],
      ["assigned_to", "Assigned"],
      ["status", "Status"],
      ["due_date", "Due"],
      ["priority", "Priority"],
    ],
  },
  {
    id: "created_today",
    title: "Jobs in today",
    hint: "MR received today",
    flag: "created_today",
    cols: [
      ["work_order_id", "MR #"],
      ["description", "Material"],
      ["department", "Site"],
      ["assigned_to", "Assigned"],
      ["status", "Status"],
      ["priority", "Priority"],
    ],
  },
  {
    id: "eta_late",
    title: "ETA missed",
    hint: "ETA / expected date is before today and not delivered",
    flag: "eta_late",
    cols: [
      ["work_order_id", "MR #"],
      ["description", "Material"],
      ["supplier", "Supplier"],
      ["po_number", "PO"],
      ["closed_date", "ETA"],
      ["days_to_eta", "Days vs ETA"],
      ["issue", "Delivery"],
    ],
  },
];

export default function ActionQueue() {
  const nav = useNavigate();
  const tick = useLiveReload();
  const { toast, ask } = useUi();
  const { can } = useAuth();
  const [filters, setFilters] = useState({});
  const [options, setOptions] = useState({});
  const { data, setData, loading } = useApiData(
    `queue:${qs(filters)}`,
    `/api/ops/queue${qs(filters)}`,
    [filters, tick]
  );

  // Print briefing: pick a date range, get the morning-digest PDF for it.
  const iso = (d) => d.toISOString().slice(0, 10);
  const [printOpen, setPrintOpen] = useState(false);
  const [printFrom, setPrintFrom] = useState("");
  const [printTo, setPrintTo] = useState("");
  const [printBusy, setPrintBusy] = useState(false);
  const [printErr, setPrintErr] = useState("");

  function openPrint() {
    const now = new Date();
    const monday = new Date(now);
    monday.setDate(now.getDate() - ((now.getDay() + 6) % 7));
    setPrintFrom(iso(monday));
    setPrintTo(iso(now));
    setPrintErr("");
    setPrintOpen(true);
  }

  function preset(days) {
    const to = new Date();
    const from = new Date();
    from.setDate(to.getDate() - days);
    setPrintFrom(iso(from));
    setPrintTo(iso(to));
  }

  async function runPrint() {
    if (!printFrom || !printTo) {
      setPrintErr("Pick both dates.");
      return;
    }
    if (printFrom > printTo) {
      setPrintErr("“From” must be on or before “To”.");
      return;
    }
    setPrintBusy(true);
    setPrintErr("");
    try {
      const blob = await api.blob(`/api/ops/digest?date_from=${printFrom}&date_to=${printTo}&fmt=pdf`);
      const url = URL.createObjectURL(blob);
      const frame = document.createElement("iframe");
      frame.style.position = "fixed";
      frame.style.right = "0";
      frame.style.bottom = "0";
      frame.style.width = "0";
      frame.style.height = "0";
      frame.style.border = "0";
      frame.src = url;
      frame.onload = () => {
        try {
          frame.contentWindow?.focus();
          frame.contentWindow?.print();
        } catch {
          window.open(url, "_blank"); // print blocked — open the PDF instead
        }
        window.setTimeout(() => {
          URL.revokeObjectURL(url);
          frame.remove();
        }, 60000);
      };
      document.body.appendChild(frame);
      setPrintOpen(false);
    } catch (e) {
      setPrintErr(e.detail || e.message || "Could not build the briefing PDF.");
    } finally {
      setPrintBusy(false);
    }
  }

  async function markSeen(row) {
    const rid = row.record_id || row.work_order_id;
    if (!rid) return;
    try {
      const d = await api.post("/api/ops/seen", { record_id: rid });
      setData((prev) => {
        if (!prev?.queues) return prev;
        const next = { ...prev, queues: {} };
        Object.entries(prev.queues).forEach(([key, rows]) => {
          next.queues[key] = (rows || []).map((r) =>
            (r.record_id || r.work_order_id) === rid ? { ...r, seen_by: d.seen_by || [] } : r
          );
        });
        return next;
      });
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function claimRow(row, force = false) {
    const rid = row.record_id || row.work_order_id;
    if (!rid) return;
    try {
      const d = await api.post(`/api/work-orders/${encodeURIComponent(rid)}/claim${force ? "?force=true" : ""}`);
      const name = d.item?.assigned_to;
      setData((prev) => {
        if (!prev?.queues) return prev;
        const next = { ...prev, queues: {} };
        Object.entries(prev.queues).forEach(([key, rows]) => {
          next.queues[key] = (rows || []).map((r) =>
            (r.record_id || r.work_order_id) === rid
              ? { ...r, assigned_to: name || r.assigned_to, seen_by: d.seen_by || r.seen_by }
              : r
          );
        });
        return next;
      });
      toast(d.already ? "Already claimed" : "Claimed", "success");
    } catch (e) {
      if (e.status === 409) {
        const ok = await ask({
          title: "Already assigned",
          body: e.detail?.message || e.message,
          confirmLabel: "Take over",
          danger: true,
        });
        if (ok) return claimRow(row, true);
        return;
      }
      toast(e.message, "error");
    }
  }

  const cachedOptions = useOptionsCache();
  useEffect(() => {
    if (cachedOptions) setOptions(cachedOptions);
  }, [cachedOptions]);



  const c = data?.counts || {};
  const go = (params) => goSearch(nav, { ...filters, ...params });

  return (
    <div className="space-y-5 briefing" data-tour="queue">
      <div className="page-head">
        <div>
          <div className="page-kicker">Daily path</div>
          <h1 className="text-2xl font-bold tracking-tight">Today’s action queue</h1>
          <p className="text-sm text-slate-500">
            What to work now · {data?.as_of || "—"} · week {data?.week || "—"}
            {loading ? " · updating…" : ""}
          </p>
        </div>
        <button className="btn-primary no-print" onClick={openPrint}>
          <Printer size={14} /> Print briefing
        </button>
      </div>

      <div className="print-only text-xs text-slate-500">
        Linkco MR morning briefing · printed {new Date().toLocaleString()} · {data?.count ?? "—"} records in view
      </div>

      <div className="no-print">
        <Filters value={filters} onChange={setFilters} options={options} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <KPICard label="Overdue" value={c.overdue} icon={AlertTriangle} accent="rose" onClick={() => go({ flag: "overdue" })} hint="Past due date" />
        <KPICard label="UNDER NTP" value={c.ntp} icon={Ban} accent="amber" onClick={() => go({ flag: "ntp" })} />
        <KPICard label="ON HOLD" value={c.on_hold} icon={PauseCircle} accent="amber" onClick={() => go({ flag: "on_hold" })} />
        <KPICard label="Due this week" value={c.due_this_week} icon={CalendarClock} accent="sky" onClick={() => go({ flag: "due_week" })} />
        <KPICard label="Due in 1–3 days" value={c.due_soon} icon={Bell} accent="amber" onClick={() => go({ flag: "due_soon" })} hint="SLA window" />
        <KPICard label="Jobs in today" value={c.created_today} icon={ClipboardList} accent="brand" onClick={() => go({ flag: "created_today" })} />
        <KPICard label="ETA missed" value={c.eta_late} icon={Truck} accent="rose" onClick={() => go({ flag: "eta_late" })} hint="Expected date passed" />
      </div>

      {SECTIONS.map((s) => (
        <OpsTable
          key={s.id}
          title={`${s.title} (${c[s.id] ?? (s.id === "due_this_week" ? c.due_this_week : 0)})`}
          subtitle={s.hint}
          rows={data?.queues?.[s.id] || []}
          columns={s.cols}
          seen
          onSeen={markSeen}
          claim={can("edit")}
          onClaim={claimRow}
          viewAll={() => go({ flag: s.flag })}
        />
      ))}
    
      {printOpen &&
        createPortal(
          <div className="fixed inset-0 z-[120] grid place-items-center p-4 bg-slate-900/55 backdrop-blur-[2px] no-print" onMouseDown={(e) => { if (e.target === e.currentTarget && !printBusy) setPrintOpen(false); }}>
            <div role="dialog" aria-modal="true" aria-label="Print briefing" className="w-full max-w-md rounded-2xl bg-white dark:bg-ink-900 border border-slate-200 dark:border-white/10 shadow-2xl p-5 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs uppercase tracking-wider text-slate-400">Print briefing</div>
                  <div className="text-lg font-bold leading-tight">Pick the period</div>
                  <div className="text-xs text-slate-500">Overdue, UNDER NTP and due-soon for the range — grouped by site and person, ready to print.</div>
                </div>
                <button type="button" className="btn-ghost !px-2" onClick={() => setPrintOpen(false)} disabled={printBusy} aria-label="Close">
                  <X size={16} />
                </button>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="lbl">From</label>
                  <input type="date" value={printFrom} onChange={(e) => setPrintFrom(e.target.value)} autoFocus />
                </div>
                <div>
                  <label className="lbl">To</label>
                  <input type="date" value={printTo} onChange={(e) => setPrintTo(e.target.value)} />
                </div>
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                <button type="button" className="btn-outline !py-1 !px-2.5" onClick={() => preset(0)}>Today</button>
                <button type="button" className="btn-outline !py-1 !px-2.5" onClick={() => preset(6)}>Last 7 days</button>
                <button type="button" className="btn-outline !py-1 !px-2.5" onClick={() => preset(29)}>Last 30 days</button>
              </div>
              {printErr && <div className="rounded-lg bg-rose-50 dark:bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">{printErr}</div>}
              <div className="flex justify-end gap-2 pt-1">
                <button type="button" className="btn-outline" disabled={printBusy} onClick={() => setPrintOpen(false)}>Cancel</button>
                <button type="button" className="btn-go" disabled={printBusy} onClick={runPrint}>
                  <Printer size={14} /> {printBusy ? "Preparing…" : "Print PDF"}
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
</div>
  );
}
