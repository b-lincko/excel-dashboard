import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  ClipboardList,
  Clock,
  FolderOpen,
  Hourglass,
  Timer,
  Truck,
  Wrench,
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
import { api, qs } from "../lib/api.js";
import KPICard from "../components/KPICard.jsx";
import Filters from "../components/Filters.jsx";
import ChartCard from "../components/ChartCard.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

const PIE = ["#0F3D5E", "#1D6A96", "#0EA5E9", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#64748B", "#14B8A6"];

export default function Dashboard() {
  const nav = useNavigate();
  const [filters, setFilters] = useState({});
  const [options, setOptions] = useState({});
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [offline, setOffline] = useState(false);
  const [loading, setLoading] = useState(true);
  const [recent, setRecent] = useState([]);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    api.get("/api/work-orders/options").then((d) => setOptions(d.options || {})).catch(() => {});
  }, []);

  useEffect(() => {
    const onData = () => setTick((n) => n + 1);
    window.addEventListener("woms:data", onData);
    return () => window.removeEventListener("woms:data", onData);
  }, []);

  const load = useCallback(() => {
    const query = qs(filters);
    return Promise.all([
      api.get(`/api/dashboard${query}`),
      api.get(`/api/work-orders${query}&page_size=8&sort=created_date`),
    ]);
  }, [filters]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    load()
      .then(([dash, table]) => {
        if (cancelled) return;
        setOffline(false);
        setError("");
        setData(dash);
        setRecent(table.items || []);
      })
      .catch((e) => {
        if (cancelled) return;
        setOffline(!!e.offline);
        setError(e.detail || e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [load, tick]);

  const k = data?.kpis || {};

  const go = (params) => {
    const sp = new URLSearchParams({ ...filters, ...params });
    [...sp.keys()].forEach((key) => {
      if (!sp.get(key)) sp.delete(key);
    });
    nav(`/work-orders?${sp.toString()}`);
  };

  if (error && !data) {
    return (
      <div className="card p-8 text-center max-w-xl mx-auto">
        <div className="text-lg font-semibold">
          {offline ? "Backend API is not running" : "Excel file is currently unavailable."}
        </div>
        <p className="text-sm text-slate-500 mt-2">{typeof error === "string" ? error : JSON.stringify(error)}</p>
        {offline && (
          <ol className="text-left text-sm text-slate-600 dark:text-slate-300 mt-4 space-y-1 list-decimal list-inside">
            <li>Run <code>run.bat</code> — it must open a window titled <b>Linkco MR API</b>.</li>
            <li>Leave that window open. It should say “Excel found” then “Uvicorn running on http://0.0.0.0:8000”.</li>
            <li>Confirm <code>file.xlsx</code> is in the same folder as <code>run.bat</code>.</li>
            <li>Refresh this page.</li>
          </ol>
        )}
      </div>
    );
  }

  const progress = Math.min(100, k.completion_rate || 0);

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Material Request dashboard</h1>
          <p className="text-sm text-slate-500">
            Live from Excel · {data?.as_of || "—"} · {data?.sync?.record_count ?? data?.count ?? "—"} records
            {loading ? " · refreshing…" : ""}
          </p>
        </div>
      </div>

      <Filters value={filters} onChange={setFilters} options={options} />

      <div className="card p-4">
        <div className="flex items-center justify-between text-sm mb-2">
          <span className="font-semibold">Overall progress</span>
          <span className="text-slate-500">{k.closed ?? 0} closed of {k.total ?? 0}</span>
        </div>
        <div className="h-3 rounded-full bg-slate-100 dark:bg-white/10 overflow-hidden">
          <div className="h-full bg-gradient-to-r from-brand-700 to-emerald-500" style={{ width: `${progress}%` }} />
        </div>
        <div className="mt-2 text-xs text-slate-500">{progress}% complete · {k.open ?? 0} still open · {k.blockades ?? 0} blocked</div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <KPICard label="Jobs in today" value={k.created_today} hint="MR received today" icon={ClipboardList} accent="brand" onClick={() => go({ period: "today" })} />
        <KPICard label="Jobs done today" value={k.done_today} hint="Closed / ETA today" icon={CheckCircle2} accent="emerald" onClick={() => go({ flag: "closed", period: "today" })} />
        <KPICard label="Delivered today" value={k.delivered_today} icon={Truck} accent="sky" />
        <KPICard label="Blockades" value={k.blockades} hint="NTP, hold, open, overdue" icon={Ban} accent="rose" onClick={() => go({ flag: "open" })} />
        <KPICard label="In progress" value={k.in_progress} hint="Placed / gatepass" icon={Wrench} accent="indigo" onClick={() => go({ flag: "in_progress" })} />
        <KPICard label="Overdue" value={k.overdue} icon={AlertTriangle} accent="rose" onClick={() => go({ flag: "overdue" })} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
        <KPICard label="Total MRs" value={k.total} icon={ClipboardList} accent="brand" onClick={() => go({})} />
        <KPICard label="Open" value={k.open} icon={FolderOpen} accent="sky" onClick={() => go({ flag: "open" })} />
        <KPICard label="Closed" value={k.closed} icon={CheckCircle2} accent="emerald" onClick={() => go({ flag: "closed" })} />
        <KPICard label="Pending / NTP" value={k.pending} icon={Hourglass} accent="amber" onClick={() => go({ flag: "pending" })} />
        <KPICard label="Completion rate" value={`${k.completion_rate ?? 0}%`} icon={CheckCircle2} accent="emerald" />
        <KPICard label="Avg close" value={k.average_closing_days != null ? `${k.average_closing_days} d` : "—"} icon={Timer} accent="brand" />
        <KPICard label="Avg aging" value={k.average_aging_days != null ? `${k.average_aging_days} d` : "—"} hint={`Oldest ${k.oldest_open_days ?? 0} d`} icon={Clock} accent="amber" />
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <ChartCard title="Last 14 days" subtitle="Created vs done" className="lg:col-span-2">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data?.last_days || []}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Bar dataKey="created" name="Created" fill="#0F3D5E" radius={[4, 4, 0, 0]} />
              <Bar dataKey="done" name="Done" fill="#10B981" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Blockades" subtitle="Why open MRs are stuck">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={data?.blockades || []} dataKey="value" nameKey="name" innerRadius={48} outerRadius={78} onClick={(d) => d?.name && go({ status: d.name, flag: "open" })}>
                {(data?.blockades || []).map((_, i) => (
                  <Cell key={i} fill={PIE[i % PIE.length]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <ChartCard title="Workload trend" subtitle="Created vs closed (12 months)" className="lg:col-span-2">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data?.trend || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="created" stroke="#0F3D5E" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="closed" stroke="#10B981" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Status" subtitle="From Excel STATUS values">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={data?.status || []} dataKey="value" nameKey="name" innerRadius={52} outerRadius={80} onClick={(d) => d?.name && go({ status: d.name })}>
                {(data?.status || []).map((_, i) => (
                  <Cell key={i} fill={PIE[i % PIE.length]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <ChartCard title="Delivery status" subtitle="Click to filter">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data?.delivery || []}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="value" fill="#0EA5E9" radius={[6, 6, 0, 0]} onClick={(d) => d?.name && go({ delay_reason: d.name })} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Open aging" subtitle="How long MRs have been outstanding">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data?.aging || []}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="value" fill="#F59E0B" radius={[6, 6, 0, 0]} onClick={(d) => d?.id && nav(`/work-orders?flag=open&aging=${d.id}`)} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <ChartCard title="Why still open?" subtitle="Status + delivery">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={(data?.reasons || []).slice(0, 8)} layout="vertical" margin={{ left: 24 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" allowDecimals={false} />
              <YAxis type="category" dataKey="name" width={160} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="value" fill="#1D6A96" radius={[0, 6, 6, 0]} onClick={(d) => d?.name && nav(`/work-orders?flag=open&reason=${encodeURIComponent(d.name)}`)} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <div className="card overflow-hidden">
          <div className="px-4 py-3 font-semibold border-b border-slate-100 dark:border-white/5">Site performance</div>
          <div className="table-wrap max-h-[280px]">
            <table className="data">
              <thead>
                <tr>
                  <th>Site</th>
                  <th>Total</th>
                  <th>Open</th>
                  <th>Closed</th>
                  <th>Overdue</th>
                  <th>%</th>
                </tr>
              </thead>
              <tbody>
                {(data?.departments || []).map((r) => (
                  <tr key={r.name} onClick={() => go({ department: r.name })}>
                    <td className="font-medium">{r.name}</td>
                    <td>{r.total}</td>
                    <td>{r.open}</td>
                    <td>{r.closed}</td>
                    <td className={r.overdue ? "text-rose-600 font-semibold" : ""}>{r.overdue}</td>
                    <td>{r.completion_rate}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="card overflow-hidden">
          <div className="px-4 py-3 font-semibold border-b border-slate-100 dark:border-white/5">Technician workload</div>
          <div className="table-wrap max-h-[280px]">
            <table className="data">
              <thead>
                <tr>
                  <th>Assigned to</th>
                  <th>Total</th>
                  <th>Open</th>
                  <th>Closed</th>
                  <th>Overdue</th>
                  <th>%</th>
                </tr>
              </thead>
              <tbody>
                {(data?.employees || []).map((r) => (
                  <tr key={r.name} onClick={() => go({ assigned_to: r.name })}>
                    <td className="font-medium">{r.name}</td>
                    <td>{r.total}</td>
                    <td>{r.open}</td>
                    <td>{r.closed}</td>
                    <td className={r.overdue ? "text-rose-600 font-semibold" : ""}>{r.overdue}</td>
                    <td>{r.completion_rate}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="card overflow-hidden">
          <div className="px-4 py-3 font-semibold border-b border-slate-100 dark:border-white/5">Priority</div>
          <div className="table-wrap max-h-[280px]">
            <table className="data">
              <thead>
                <tr>
                  <th>Priority</th>
                  <th>Total</th>
                  <th>Open</th>
                  <th>Closed</th>
                  <th>Overdue</th>
                </tr>
              </thead>
              <tbody>
                {(data?.priorities || []).map((r) => (
                  <tr key={r.name} onClick={() => go({ priority: r.name })}>
                    <td>{r.name}</td>
                    <td>{r.total}</td>
                    <td>{r.open}</td>
                    <td>{r.closed}</td>
                    <td>{r.overdue}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

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
              {recent.map((r) => (
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
    </div>
  );
}
