import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Ban, Bell, CalendarClock, ClipboardList, PauseCircle, Printer, Truck } from "lucide-react";
import { api, qs } from "../lib/api.js";
import { goSearch, useLiveReload } from "../lib/live.js";
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
      ["work_order_id", "IM WO #"],
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
      ["work_order_id", "IM WO #"],
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
      ["work_order_id", "IM WO #"],
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
      ["work_order_id", "IM WO #"],
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
      ["work_order_id", "IM WO #"],
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
      ["work_order_id", "IM WO #"],
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
      ["work_order_id", "IM WO #"],
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
  const { toast } = useUi();
  const [filters, setFilters] = useState({});
  const [options, setOptions] = useState({});
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

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

  useEffect(() => {
    api.get("/api/work-orders/options").then((d) => setOptions(d.options || {})).catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!data) setLoading(true);
    api
      .get(`/api/ops/queue${qs(filters)}`)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filters, tick]);

  const c = data?.counts || {};
  const go = (params) => goSearch(nav, { ...filters, ...params });

  return (
    <div className="space-y-5 briefing">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Today’s action queue</h1>
          <p className="text-sm text-slate-500">
            What to work now · {data?.as_of || "—"} · week {data?.week || "—"} · live from Excel
            {loading ? " · updating…" : ""}
          </p>
        </div>
        <button className="btn-primary no-print" onClick={() => window.print()}>
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
          viewAll={() => go({ flag: s.flag })}
        />
      ))}
    </div>
  );
}
