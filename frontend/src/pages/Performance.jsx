import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../lib/api.js";
import { useLiveReload } from "../lib/live.js";
import ChartCard from "../components/ChartCard.jsx";
import KPICard from "../components/KPICard.jsx";

export default function Performance() {
  const nav = useNavigate();
  const tick = useLiveReload();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => {
    api
      .get("/api/dashboard/performance")
      .then(setData)
      .catch((e) => setError(e.message));
  }, [tick]);

  const rows = (data?.employees || []).filter((r) => !q || r.name.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Employee performance</h1>
        <p className="text-sm text-slate-500">
          Live metrics from Excel — open vs placed vs closed, overdue load, and closing speed by assignee.
        </p>
      </div>
      {error && <div className="rounded-xl bg-rose-50 text-rose-800 px-4 py-3 text-sm">{error}</div>}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <KPICard label="Assignees" value={data?.employees?.length} hint="People with at least one MR" />
        <KPICard label="Open" value={data?.kpis?.open} accent="sky" onClick={() => nav("/open")} />
        <KPICard label="Placed" value={data?.kpis?.placed} accent="indigo" onClick={() => nav("/placed")} />
        <KPICard label="Overdue" value={data?.kpis?.overdue} accent="rose" onClick={() => nav("/overdue")} />
        <KPICard label="Completion" value={data?.kpis?.completion_rate != null ? `${data.kpis.completion_rate}%` : "—"} accent="emerald" />
      </div>
      <ChartCard title="Workload by assignee" subtitle="Click a bar to open that person’s material requests">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data?.workload || []}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" interval={0} angle={-25} textAnchor="end" height={70} tick={{ fontSize: 11 }} />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Legend />
            <Bar dataKey="open" fill="#0EA5E9" isAnimationActive={false} cursor="pointer" onClick={(d) => d?.name && nav(`/work-orders?assigned_to=${encodeURIComponent(d.name)}&flag=open`)} />
            <Bar dataKey="placed" fill="#6366F1" isAnimationActive={false} cursor="pointer" onClick={(d) => d?.name && nav(`/work-orders?assigned_to=${encodeURIComponent(d.name)}&flag=placed`)} />
            <Bar dataKey="overdue" fill="#EF4444" isAnimationActive={false} cursor="pointer" onClick={(d) => d?.name && nav(`/work-orders?assigned_to=${encodeURIComponent(d.name)}&flag=overdue`)} />
            <Bar dataKey="closed" fill="#10B981" isAnimationActive={false} cursor="pointer" onClick={(d) => d?.name && nav(`/work-orders?assigned_to=${encodeURIComponent(d.name)}&flag=closed`)} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
      <ChartCard title="Completion rate" subtitle="Closed ÷ assigned">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data?.completion || []}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" interval={0} angle={-25} textAnchor="end" height={70} tick={{ fontSize: 11 }} />
            <YAxis domain={[0, 100]} />
            <Tooltip />
            <Bar dataKey="completion_rate" fill="#0F3D5E" isAnimationActive={false} cursor="pointer" onClick={(d) => d?.name && nav(`/work-orders?assigned_to=${encodeURIComponent(d.name)}`)} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
      <div className="card overflow-hidden">
        <div className="px-4 py-3 flex items-center justify-between gap-3">
          <div className="font-semibold">People</div>
          <input className="max-w-xs" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter assignee…" />
        </div>
        <table className="data">
          <thead>
            <tr>
              <th>Assignee</th>
              <th>Total</th>
              <th>Open</th>
              <th>Placed</th>
              <th>Pending</th>
              <th>Closed</th>
              <th>Overdue</th>
              <th>Completion</th>
              <th>Avg close (d)</th>
              <th>Avg aging (d)</th>
              <th>Oldest open</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name} onClick={() => nav(`/work-orders?assigned_to=${encodeURIComponent(r.name)}`)}>
                <td className="font-medium">{r.name}</td>
                <td>{r.total}</td>
                <td>{r.open}</td>
                <td>{r.placed}</td>
                <td>{r.pending}</td>
                <td>{r.closed}</td>
                <td className={r.overdue ? "text-rose-600 font-semibold" : ""}>{r.overdue}</td>
                <td>{r.completion_rate}%</td>
                <td>{r.average_closing_days ?? "—"}</td>
                <td>{r.average_aging_days ?? "—"}</td>
                <td>{r.oldest_open_days || "—"}</td>
              </tr>
            ))}
            {!rows.length && (
              <tr className="!cursor-default">
                <td colSpan={11} className="text-center text-slate-400 py-8">
                  No assignees in the current Excel data.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
