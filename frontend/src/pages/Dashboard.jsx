import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Clock,
  FolderOpen,
  Hourglass,
  Timer,
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
  const [loading, setLoading] = useState(true);
  const [recent, setRecent] = useState([]);

  useEffect(() => {
    api.get("/api/work-orders/options").then((d) => setOptions(d.options || {})).catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    const query = qs(filters);
    Promise.all([api.get(`/api/dashboard${query}`), api.get(`/api/work-orders${query}&page_size=8&sort=last_updated`)])
      .then(([dash, table]) => {
        if (cancelled) return;
        setData(dash);
        setRecent(table.items || []);
      })
      .catch((e) => {
        if (!cancelled) setError(e.detail || e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filters]);

  const k = data?.kpis || {};

  const go = (params) => {
    const sp = new URLSearchParams({ ...filters, ...params });
    [...sp.keys()].forEach((key) => {
      if (!sp.get(key)) sp.delete(key);
    });
    nav(`/work-orders?${sp.toString()}`);
  };

  const tooltipStyle = useMemo(
    () => ({ background: "var(--tw-bg, #0B1220)", border: "1px solid #1e293b", borderRadius: 8, fontSize: 12 }),
    []
  );

  if (error) {
    return (
      <div className="card p-8 text-center">
        <div className="text-lg font-semibold">Excel file is currently unavailable.</div>
        <p className="text-sm text-slate-500 mt-2">{typeof error === "string" ? error : JSON.stringify(error)}</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Material Request dashboard</h1>
          <p className="text-sm text-slate-500">Live statistics from Linkco MR logs — Shield 5 / Shield 1 and Falcon 5.</p>
        </div>
        <div className="text-xs text-slate-400">
          {data?.sync?.record_count ?? "—"} records · token {data?.sync?.sync_token || "—"}
        </div>
      </div>

      <Filters value={filters} onChange={setFilters} options={options} />

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
        <KPICard label="Total material requests" value={k.total} icon={ClipboardList} accent="brand" onClick={() => go({})} />
        <KPICard label="Open" value={k.open} icon={FolderOpen} accent="sky" onClick={() => go({ flag: "open" })} />
        <KPICard label="Closed" value={k.closed} icon={CheckCircle2} accent="emerald" onClick={() => go({ flag: "closed" })} />
        <KPICard label="Overdue" value={k.overdue} icon={AlertTriangle} accent="rose" onClick={() => go({ flag: "overdue" })} />
        <KPICard label="In progress" value={k.in_progress} icon={Wrench} accent="indigo" onClick={() => go({ flag: "in_progress" })} />
        <KPICard label="Pending" value={k.pending} icon={Hourglass} accent="amber" onClick={() => go({ flag: "pending" })} />
        <KPICard label="Completion rate" value={`${k.completion_rate ?? 0}%`} hint="Closed / Total × 100" icon={CheckCircle2} accent="emerald" />
        <KPICard
          label="Avg closing time"
          value={k.average_closing_days != null ? `${k.average_closing_days} d` : "—"}
          hint="Created → closed"
          icon={Timer}
          accent="brand"
        />
        <KPICard
          label="Avg aging (open)"
          value={k.average_aging_days != null ? `${k.average_aging_days} d` : "—"}
          hint={`Oldest ${k.oldest_open_days ?? 0} days`}
          icon={Clock}
          accent="amber"
        />
      </div>

      {loading && <div className="text-sm text-slate-400">Refreshing from Excel…</div>}

      <div className="grid lg:grid-cols-3 gap-4">
        <ChartCard title="Workload trend" subtitle="Created vs closed (last 12 months)" className="lg:col-span-2">
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
        <ChartCard title="Status distribution" subtitle="From actual Excel status values">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data?.status || []}
                dataKey="value"
                nameKey="name"
                innerRadius={52}
                outerRadius={80}
                onClick={(d) => d?.name && go({ status: d.name })}
              >
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
        <ChartCard title="Why are work orders still open?" subtitle="Click a reason to drill down">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={(data?.reasons || []).slice(0, 8)} layout="vertical" margin={{ left: 24 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" allowDecimals={false} />
              <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar
                dataKey="value"
                fill="#1D6A96"
                radius={[0, 6, 6, 0]}
                onClick={(d) => d?.name && nav(`/work-orders?flag=open&reason=${encodeURIComponent(d.name)}`)}
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Open work order aging" subtitle="Click a bucket to see the orders">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data?.aging || []}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar
                dataKey="value"
                fill="#F59E0B"
                radius={[6, 6, 0, 0]}
                onClick={(d) => d?.id && nav(`/work-orders?flag=open&aging=${d.id}`)}
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="card overflow-hidden">
          <div className="px-4 py-3 font-semibold border-b border-slate-100 dark:border-white/5">Department performance</div>
          <div className="table-wrap max-h-[320px]">
            <table className="data">
              <thead>
                <tr>
                  <th>Department</th>
                  <th>Total</th>
                  <th>Open</th>
                  <th>Closed</th>
                  <th>Overdue</th>
                  <th>Completion</th>
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
        <div className="card overflow-hidden">
          <div className="px-4 py-3 font-semibold border-b border-slate-100 dark:border-white/5">Technician workload</div>
          <div className="table-wrap max-h-[320px]">
            <table className="data">
              <thead>
                <tr>
                  <th>Assigned to</th>
                  <th>Total</th>
                  <th>Open</th>
                  <th>Closed</th>
                  <th>Overdue</th>
                  <th>Completion</th>
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
      </div>

      <div className="card overflow-hidden">
        <div className="px-4 py-3 flex items-center justify-between border-b border-slate-100 dark:border-white/5">
          <div className="font-semibold">Recently updated</div>
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
                <th>Department</th>
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
