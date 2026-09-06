import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ClipboardList,
  Clock,
  FolderOpen,
  Hourglass,
  Plus,
  Timer,
  Trash2,
  Truck,
  Wrench,
  X,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import KPICard from "./KPICard.jsx";
import ChartCard from "./ChartCard.jsx";
import StatusBadge from "./StatusBadge.jsx";
import MindMap from "./MindMap.jsx";
import CustomChart from "./CustomChart.jsx";
import {
  CATALOG,
  CHART_STYLES,
  DATASETS,
  GROUP_METRICS,
  KPI_METRICS,
  MINDMAP_BRANCHES,
  buildMindmap,
  datasetById,
  metricValue,
} from "../lib/widgets.js";

const PIE = ["#0F3D5E", "#1D6A96", "#0EA5E9", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#64748B", "#14B8A6"];

const ICONS = {
  created_today: ClipboardList,
  done_today: CheckCircle2,
  delivered_today: Truck,
  blockades: Ban,
  in_progress: Wrench,
  overdue: AlertTriangle,
  total: ClipboardList,
  open: FolderOpen,
  closed: CheckCircle2,
  pending: Hourglass,
  completion_rate: CheckCircle2,
  average_closing_days: Timer,
  average_aging_days: Clock,
};

function spanClass(span) {
  if (span === "full") return "lg:col-span-3";
  if (span === "2") return "lg:col-span-2";
  return "lg:col-span-1";
}

function GroupTable({ title, rows, onRow, columns, showRate = true }) {
  return (
    <div className="card overflow-hidden h-full">
      <div className="px-4 py-3 font-semibold border-b border-slate-100 dark:border-white/5">{title}</div>
      <div className="table-wrap max-h-[280px]">
        <table className="data">
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(rows || []).map((r) => (
              <tr key={r.name} onClick={() => onRow && onRow(r)}>
                <td className="font-medium">{r.name}</td>
                <td>{r.total}</td>
                <td>{r.open}</td>
                <td>{r.closed}</td>
                <td className={r.overdue ? "text-rose-600 font-semibold" : ""}>{r.overdue}</td>
                {showRate ? <td>{r.completion_rate}%</td> : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function WidgetBoard({ data, recent, go, layout, editing, onChange }) {
  const nav = useNavigate();
  const k = data?.kpis || {};

  function update(id, patch) {
    onChange(layout.map((w) => (w.id === id ? { ...w, ...patch } : w)));
  }
  function remove(id) {
    onChange(layout.filter((w) => w.id !== id));
  }
  function move(id, dir) {
    const i = layout.findIndex((w) => w.id === id);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= layout.length) return;
    const next = layout.slice();
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  }

  function renderBody(w) {
    switch (w.type) {
      case "progress": {
        const progress = Math.min(100, k.completion_rate || 0);
        return (
          <div className="card p-4">
            <div className="flex items-center justify-between text-sm mb-2">
              <span className="font-semibold">Overall progress</span>
              <span className="text-slate-500">
                {k.closed ?? 0} closed of {k.total ?? 0}
              </span>
            </div>
            <div className="h-3 rounded-full bg-slate-100 dark:bg-white/10 overflow-hidden">
              <div className="h-full bg-gradient-to-r from-brand-700 to-emerald-500" style={{ width: `${progress}%` }} />
            </div>
            <div className="mt-2 text-xs text-slate-500">
              {progress}% complete · {k.open ?? 0} still open · {k.blockades ?? 0} blocked
            </div>
          </div>
        );
      }
      case "kpis_today":
        return (
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
            <KPICard label="Jobs in today" value={k.created_today} hint="MR received today" icon={ClipboardList} accent="brand" onClick={() => go({ period: "today" })} />
            <KPICard label="Jobs done today" value={k.done_today} hint="Closed / ETA today" icon={CheckCircle2} accent="emerald" onClick={() => go({ flag: "closed", period: "today" })} />
            <KPICard label="Delivered today" value={k.delivered_today} icon={Truck} accent="sky" />
            <KPICard label="Blockades" value={k.blockades} hint="NTP, hold, open, overdue" icon={Ban} accent="rose" onClick={() => go({ flag: "open" })} />
            <KPICard label="In progress" value={k.in_progress} hint="Placed / gatepass" icon={Wrench} accent="indigo" onClick={() => go({ flag: "in_progress" })} />
            <KPICard label="Overdue" value={k.overdue} icon={AlertTriangle} accent="rose" onClick={() => go({ flag: "overdue" })} />
          </div>
        );
      case "action_queue": {
        const o = data?.ops || {};
        return (
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
            <KPICard label="Overdue" value={o.overdue} icon={AlertTriangle} accent="rose" onClick={() => go({ flag: "overdue" })} />
            <KPICard label="UNDER NTP" value={o.ntp} icon={Ban} accent="amber" onClick={() => go({ flag: "ntp" })} />
            <KPICard label="ON HOLD" value={o.on_hold} icon={Hourglass} accent="amber" onClick={() => go({ flag: "on_hold" })} />
            <KPICard label="Due this week" value={o.due_this_week} icon={Timer} accent="sky" onClick={() => go({ flag: "due_week" })} />
            <KPICard label="Jobs in today" value={o.created_today} icon={ClipboardList} accent="brand" onClick={() => go({ flag: "created_today" })} />
            <KPICard label="ETA missed" value={o.eta_late} icon={Truck} accent="rose" onClick={() => go({ flag: "eta_late" })} />
          </div>
        );
      }
      case "supplier_kpis": {
        const o = data?.ops || {};
        return (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KPICard label="Suppliers" value={o.suppliers} icon={ClipboardList} accent="brand" onClick={() => nav("/suppliers")} />
            <KPICard label="Pending POs" value={o.pending_po} icon={Truck} accent="sky" onClick={() => go({ flag: "pending_po" })} />
            <KPICard label="Awaiting PO" value={o.awaiting_po} icon={Hourglass} accent="amber" onClick={() => go({ flag: "awaiting_po" })} />
            <KPICard label="ETA missed" value={o.eta_late} icon={AlertTriangle} accent="rose" onClick={() => go({ flag: "eta_late" })} />
          </div>
        );
      }
      case "kpis_totals":
        return (
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
            <KPICard label="Total MRs" value={k.total} icon={ClipboardList} accent="brand" onClick={() => go({})} />
            <KPICard label="Open" value={k.open} icon={FolderOpen} accent="sky" onClick={() => go({ flag: "open" })} />
            <KPICard label="Closed" value={k.closed} icon={CheckCircle2} accent="emerald" onClick={() => go({ flag: "closed" })} />
            <KPICard label="Pending / NTP" value={k.pending} icon={Hourglass} accent="amber" onClick={() => go({ flag: "pending" })} />
            <KPICard label="Completion rate" value={`${k.completion_rate ?? 0}%`} icon={CheckCircle2} accent="emerald" />
            <KPICard label="Avg close" value={k.average_closing_days != null ? `${k.average_closing_days} d` : "—"} icon={Timer} accent="brand" />
            <KPICard label="Avg aging" value={k.average_aging_days != null ? `${k.average_aging_days} d` : "—"} hint={`Oldest ${k.oldest_open_days ?? 0} d`} icon={Clock} accent="amber" />
          </div>
        );
      case "kpi": {
        const meta = KPI_METRICS.find((m) => m.id === w.metric) || KPI_METRICS[0];
        let value = k[meta.id];
        if (meta.suffix && value != null) value = `${value}${meta.suffix}`;
        return (
          <KPICard
            label={meta.label}
            value={value}
            icon={ICONS[meta.id]}
            accent={meta.accent}
            hint="Click to view records"
            onClick={() => {
              if (meta.id === "open") go({ flag: "open" });
              else if (meta.id === "closed") go({ flag: "closed" });
              else if (meta.id === "overdue") go({ flag: "overdue" });
              else if (meta.id === "pending") go({ flag: "pending" });
              else if (meta.id === "in_progress") go({ flag: "in_progress" });
              else if (meta.id === "created_today" || meta.id === "done_today") go({ period: "today" });
              else go({});
            }}
          />
        );
      }
      case "mindmap":
        return <MindMap data={data?.mindmap} />;
      case "chart_last_days":
        return (
          <ChartCard title="Last 14 days" subtitle="Created vs done">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data?.last_days || []}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Legend />
                <Bar dataKey="created" name="Created" fill="#0F3D5E" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                <Bar dataKey="done" name="Done" fill="#10B981" radius={[4, 4, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        );
      case "chart_blockades":
        return (
          <ChartCard title="Blockades" subtitle="Why open MRs are stuck">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={data?.blockades || []} dataKey="value" nameKey="name" innerRadius={48} outerRadius={78} isAnimationActive={false} onClick={(d) => d?.name && go({ status: d.name, flag: "open" })}>
                  {(data?.blockades || []).map((_, i) => (
                    <Cell key={i} fill={PIE[i % PIE.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </ChartCard>
        );
      case "chart_trend":
        return (
          <ChartCard title="Workload trend" subtitle="Created vs closed (12 months)">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data?.trend || []}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="created" stroke="#0F3D5E" strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="closed" stroke="#10B981" strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>
        );
      case "chart_status":
        return (
          <ChartCard title="Status" subtitle="From Excel STATUS values">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={data?.status || []} dataKey="value" nameKey="name" innerRadius={52} outerRadius={80} isAnimationActive={false} onClick={(d) => d?.name && go({ status: d.name })}>
                  {(data?.status || []).map((_, i) => (
                    <Cell key={i} fill={PIE[i % PIE.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </ChartCard>
        );
      case "chart_delivery":
        return (
          <ChartCard title="Delivery status" subtitle="Click to filter">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data?.delivery || []}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="value" fill="#0EA5E9" radius={[6, 6, 0, 0]} isAnimationActive={false} onClick={(d) => d?.name && go({ delay_reason: d.name })} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        );
      case "chart_aging":
        return (
          <ChartCard title="Open aging" subtitle="How long MRs have been outstanding">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data?.aging || []}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="value" fill="#F59E0B" radius={[6, 6, 0, 0]} isAnimationActive={false} onClick={(d) => d?.id && nav(`/work-orders?flag=open&aging=${d.id}`)} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        );
      case "chart_reasons":
        return (
          <ChartCard title="Why still open?" subtitle="Status + delivery">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={(data?.reasons || []).slice(0, 8)} layout="vertical" margin={{ left: 24 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" allowDecimals={false} />
                <YAxis type="category" dataKey="name" width={160} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="value" fill="#1D6A96" radius={[0, 6, 6, 0]} isAnimationActive={false} onClick={(d) => d?.name && nav(`/work-orders?flag=open&reason=${encodeURIComponent(d.name)}`)} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        );
      case "table_sites":
        return <GroupTable title="Site performance" rows={data?.departments} onRow={(r) => go({ department: r.name })} columns={["Site", "Total", "Open", "Closed", "Overdue", "%"]} />;
      case "table_people":
        return <GroupTable title="Technician workload" rows={data?.employees} onRow={(r) => go({ assigned_to: r.name })} columns={["Assigned to", "Total", "Open", "Closed", "Overdue", "%"]} />;
      case "table_priority":
        return <GroupTable title="Priority" rows={data?.priorities} onRow={(r) => go({ priority: r.name })} columns={["Priority", "Total", "Open", "Closed", "Overdue"]} showRate={false} />;
      case "table_types":
        return <GroupTable title="Purchase type" rows={data?.work_types} onRow={(r) => go({ work_type: r.name })} columns={["Type", "Total", "Open", "Closed", "Overdue", "%"]} />;
      case "table_recent":
        return (
          <div className="card overflow-hidden">
            <div className="px-4 py-3 flex items-center justify-between border-b border-slate-100 dark:border-white/5">
              <div className="font-semibold">Latest material requests</div>
              <button className="btn-ghost text-sm" onClick={() => nav("/work-orders")}>
                View all
              </button>
            </div>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>WO #</th>
                    <th>Description</th>
                    <th>Site</th>
                    <th>Assigned</th>
                    <th>Priority</th>
                    <th>Status</th>
                    <th>Due</th>
                  </tr>
                </thead>
                <tbody>
                  {(recent || data?.recent || []).map((r) => (
                    <tr key={r.record_id || r.work_order_id} onClick={() => nav(`/work-orders/${encodeURIComponent(r.record_id || r.work_order_id)}`)}>
                      <td className="font-mono text-xs font-semibold">{r.work_order_id}</td>
                      <td className="max-w-xs truncate">{r.description}</td>
                      <td>{r.department}</td>
                      <td>{r.assigned_to}</td>
                      <td>
                        <StatusBadge value={r.priority} />
                      </td>
                      <td>
                        <StatusBadge value={r.status} />
                      </td>
                      <td>{(r.due_date || "").slice(0, 10)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      default:
        return <div className="card p-4 text-sm text-slate-500">Unknown widget: {w.type}</div>;
    }
  }

  return (
    <div className="grid lg:grid-cols-3 gap-4">
      {layout.map((w) => (
        <div key={w.id} className={`${spanClass(w.span)} ${editing ? "widget-edit" : ""}`}>
          {editing && (
            <div className="flex items-center gap-1 mb-1 text-xs">
              <button className="btn-ghost !px-1.5 !py-1" onClick={() => move(w.id, -1)} title="Move up">
                <ChevronUp size={14} />
              </button>
              <button className="btn-ghost !px-1.5 !py-1" onClick={() => move(w.id, 1)} title="Move down">
                <ChevronDown size={14} />
              </button>
              <select className="w-auto !py-1 !px-2 text-xs" value={w.span || "1"} onChange={(e) => update(w.id, { span: e.target.value })}>
                <option value="1">Narrow</option>
                <option value="2">Wide</option>
                <option value="full">Full width</option>
              </select>
              {w.type === "kpi" && (
                <select className="w-auto !py-1 !px-2 text-xs" value={w.metric || "open"} onChange={(e) => update(w.id, { metric: e.target.value })}>
                  {KPI_METRICS.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              )}
              {(w.type === "chart_custom" || w.type === "table_custom") && (
                <select className="w-auto !py-1 !px-2 text-xs" value={w.dataset || "status"} onChange={(e) => update(w.id, { dataset: e.target.value })}>
                  {(w.type === "table_custom" ? DATASETS.filter((d) => d.kind === "group") : DATASETS).map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.label}
                    </option>
                  ))}
                </select>
              )}
              {w.type === "chart_custom" && (
                <>
                  <select className="w-auto !py-1 !px-2 text-xs" value={w.style || "bar"} onChange={(e) => update(w.id, { style: e.target.value })}>
                    {CHART_STYLES.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                  {datasetById(w.dataset).kind === "group" && (
                    <select className="w-auto !py-1 !px-2 text-xs" value={w.metric || "total"} onChange={(e) => update(w.id, { metric: e.target.value })}>
                      {GROUP_METRICS.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.label}
                        </option>
                      ))}
                    </select>
                  )}
                </>
              )}
              {w.type === "mindmap_custom" && (
                <div className="flex flex-wrap gap-1.5 items-center">
                  {MINDMAP_BRANCHES.map((b) => {
                    const on = (w.branches || []).includes(b.id);
                    return (
                      <button
                        key={b.id}
                        type="button"
                        className={`btn-outline !py-0.5 !px-2 text-[11px] ${on ? "!bg-brand-700 !text-white !border-brand-700" : ""}`}
                        onClick={() => {
                          const cur = w.branches || [];
                          update(w.id, { branches: on ? cur.filter((x) => x !== b.id) : [...cur, b.id] });
                        }}
                      >
                        {b.label}
                      </button>
                    );
                  })}
                </div>
              )}
              <button className="btn-ghost !px-1.5 !py-1 ml-auto text-rose-600" onClick={() => remove(w.id)} title="Remove">
                <Trash2 size={14} />
              </button>
            </div>
          )}
          {renderBody(w)}
        </div>
      ))}
    </div>
  );
}

export function AddWidgetBar({ onAdd, onClose }) {
  const groups = {};
  CATALOG.forEach((c) => {
    (groups[c.category] ||= []).push(c);
  });
  const [dataset, setDataset] = useState("status");
  const [style, setStyle] = useState("bar");
  const [metric, setMetric] = useState("total");
  const [kpi, setKpi] = useState("open");
  const [tableDs, setTableDs] = useState("department");
  const [branches, setBranches] = useState(["sites", "status", "blockades"]);
  const ds = datasetById(dataset);

  function toggleBranch(id) {
    setBranches((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  return (
    <div className="card p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div className="font-semibold flex items-center gap-2">
          <Plus size={16} /> Create or add widgets
        </div>
        <button className="btn-ghost !px-2 !py-1" onClick={onClose}>
          <X size={16} />
        </button>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="rounded-xl border border-slate-200 dark:border-white/10 p-3 space-y-2">
          <div className="text-[11px] uppercase tracking-wide text-slate-500">Create a graph</div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="lbl">Data</label>
              <select value={dataset} onChange={(e) => setDataset(e.target.value)}>
                {DATASETS.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="lbl">Style</label>
              <select value={style} onChange={(e) => setStyle(e.target.value)}>
                {CHART_STYLES.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            {ds.kind === "group" && (
              <div className="col-span-2">
                <label className="lbl">Metric</label>
                <select value={metric} onChange={(e) => setMetric(e.target.value)}>
                  {GROUP_METRICS.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
          <button className="btn-primary w-full" onClick={() => onAdd("chart_custom", { dataset, style, metric, span: style === "hbar" || ds.kind === "series" ? "2" : "1" })}>
            Add graph
          </button>
        </div>

        <div className="rounded-xl border border-slate-200 dark:border-white/10 p-3 space-y-2">
          <div className="text-[11px] uppercase tracking-wide text-slate-500">Create a number</div>
          <label className="lbl">Metric</label>
          <select value={kpi} onChange={(e) => setKpi(e.target.value)}>
            {KPI_METRICS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
          <button className="btn-primary w-full" onClick={() => onAdd("kpi", { metric: kpi, span: "1" })}>
            Add number
          </button>
        </div>

        <div className="rounded-xl border border-slate-200 dark:border-white/10 p-3 space-y-2">
          <div className="text-[11px] uppercase tracking-wide text-slate-500">Create a table</div>
          <label className="lbl">Group by</label>
          <select value={tableDs} onChange={(e) => setTableDs(e.target.value)}>
            {DATASETS.filter((d) => d.kind === "group").map((d) => (
              <option key={d.id} value={d.id}>
                {d.label}
              </option>
            ))}
          </select>
          <button className="btn-primary w-full" onClick={() => onAdd("table_custom", { dataset: tableDs, span: "1" })}>
            Add table
          </button>
        </div>

        <div className="rounded-xl border border-slate-200 dark:border-white/10 p-3 space-y-2">
          <div className="text-[11px] uppercase tracking-wide text-slate-500">Create a mind map</div>
          <div className="flex flex-wrap gap-2">
            {MINDMAP_BRANCHES.map((b) => (
              <label key={b.id} className="flex items-center gap-1.5 text-xs">
                <input type="checkbox" className="w-auto" checked={branches.includes(b.id)} onChange={() => toggleBranch(b.id)} />
                {b.label}
              </label>
            ))}
          </div>
          <button
            className="btn-primary w-full"
            disabled={!branches.length}
            onClick={() => onAdd("mindmap_custom", { branches, span: "full" })}
          >
            Add mind map
          </button>
        </div>
      </div>

      {Object.entries(groups).map(([cat, items]) => (
        <div key={cat}>
          <div className="text-[11px] uppercase tracking-wide text-slate-500 mb-2">{cat}</div>
          <div className="flex flex-wrap gap-2">
            {items.map((item) => (
              <button key={item.type} className="btn-outline !py-1.5 !px-3 text-xs" onClick={() => onAdd(item.type)}>
                {item.label}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
