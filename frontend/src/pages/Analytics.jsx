import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, qs } from "../lib/api.js";
import { goSearch, useLiveReload } from "../lib/live.js";
import ChartCard from "../components/ChartCard.jsx";
import KPICard from "../components/KPICard.jsx";

const TABS = [
  ["weekly", "Weekly"],
  ["monthly", "Monthly"],
  ["yearly", "Yearly"],
  ["reasons", "Why not closed"],
  ["aging", "Aging"],
  ["priority", "Priority"],
];

export default function Analytics() {
  const nav = useNavigate();
  const tick = useLiveReload();
  const [tab, setTab] = useState("weekly");
  const yearNow = new Date().getFullYear();
  const [year, setYear] = useState(yearNow);
  const [week, setWeek] = useState("");
  const [weekly, setWeekly] = useState(null);
  const [monthly, setMonthly] = useState(null);
  const [yearly, setYearly] = useState(null);
  const [dash, setDash] = useState(null);

  const go = (params) => goSearch(nav, params);

  useEffect(() => {
    const params = { year };
    if (week) params.week = week;
    api
      .get(`/api/dashboard/weekly${qs(params)}`)
      .then((d) => {
        setWeekly(d);
        if (!week && d.week) setWeek(String(d.week));
      })
      .catch(() => {});
  }, [year, week, tick]);

  useEffect(() => {
    api.get(`/api/dashboard/monthly?year=${year}`).then(setMonthly).catch(() => {});
  }, [year, tick]);

  useEffect(() => {
    api.get("/api/dashboard/yearly").then(setYearly).catch(() => {});
    api.get("/api/dashboard").then(setDash).catch(() => {});
  }, [tick]);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Analytics</h1>
        <p className="text-sm text-slate-500">All figures are computed from the live Excel workbook. Click a number to open the matching records.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            className={tab === id ? "btn-primary" : "btn-outline"}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "weekly" && (
        <div className="space-y-4">
          <div className="flex gap-3 items-end">
            <div>
              <label className="lbl">Year</label>
              <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} />
            </div>
            <div>
              <label className="lbl">ISO week</label>
              <input
                type="number"
                min={1}
                max={53}
                value={week}
                onChange={(e) => setWeek(e.target.value)}
              />
            </div>
            <div className="text-sm text-slate-500 pb-2">{weekly?.label} · {weekly?.start} → {weekly?.end}</div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KPICard
              label="Created this week"
              value={weekly?.kpis?.total}
              hint="Click to view these MRs"
              onClick={() => go({ year: weekly?.year, week: weekly?.week })}
            />
            <KPICard
              label="Open"
              value={weekly?.kpis?.open}
              accent="sky"
              hint="Still open from this week"
              onClick={() => go({ year: weekly?.year, week: weekly?.week, flag: "open" })}
            />
            <KPICard
              label="Closed"
              value={weekly?.kpis?.closed}
              accent="emerald"
              hint="Closed of this week's MRs"
              onClick={() => go({ year: weekly?.year, week: weekly?.week, flag: "closed" })}
            />
            <KPICard
              label="Overdue"
              value={weekly?.kpis?.overdue}
              accent="rose"
              hint="Overdue from this week"
              onClick={() => go({ year: weekly?.year, week: weekly?.week, flag: "overdue" })}
            />
          </div>
          <ChartCard title={weekly?.label || "Weekly analysis"} subtitle="Click a bar to open that day's created MRs">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={weekly?.days || []}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Legend />
                <Bar dataKey="created" fill="#0F3D5E" isAnimationActive={false} cursor="pointer" onClick={(d) => d?.date && go({ date_from: d.date, date_to: d.date })} />
                <Bar dataKey="completed" fill="#0EA5E9" isAnimationActive={false} cursor="pointer" onClick={(d) => d?.date && go({ date_from: d.date, date_to: d.date })} />
                <Bar dataKey="closed" fill="#10B981" isAnimationActive={false} cursor="pointer" onClick={(d) => d?.date && go({ date_from: d.date, date_to: d.date, flag: "closed" })} />
                <Bar dataKey="open" fill="#F59E0B" isAnimationActive={false} cursor="pointer" onClick={() => go({ flag: "open" })} />
                <Bar dataKey="overdue" fill="#EF4444" isAnimationActive={false} cursor="pointer" onClick={() => go({ flag: "overdue" })} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      )}

      {tab === "monthly" && (
        <div className="space-y-4">
          <div className="w-40">
            <label className="lbl">Year</label>
            <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KPICard label="Created" value={monthly?.kpis?.total} hint="Click to view" onClick={() => go({ year })} />
            <KPICard label="Closed" value={monthly?.kpis?.closed} accent="emerald" hint="Click to view" onClick={() => go({ year, flag: "closed" })} />
            <KPICard label="Open" value={monthly?.kpis?.open} accent="sky" hint="Click to view" onClick={() => go({ year, flag: "open" })} />
            <KPICard label="Overdue" value={monthly?.kpis?.overdue} accent="rose" hint="Click to view" onClick={() => go({ year, flag: "overdue" })} />
          </div>
          <ChartCard title={`Monthly trend — ${year}`} subtitle="Click a point to open that month">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={monthly?.months || []}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Legend />
                <Line dataKey="created" stroke="#0F3D5E" isAnimationActive={false} />
                <Line dataKey="closed" stroke="#10B981" isAnimationActive={false} />
                <Line dataKey="overdue" stroke="#EF4444" isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>
          <div className="card overflow-hidden">
            <table className="data">
              <thead>
                <tr>
                  <th>Month</th>
                  <th>Created</th>
                  <th>Completed</th>
                  <th>Closed</th>
                  <th>Open (snapshot)</th>
                  <th>Overdue</th>
                  <th>Completion %</th>
                </tr>
              </thead>
              <tbody>
                {(monthly?.months || []).map((m) => (
                  <tr key={m.month} onClick={() => go({ year, month: m.month })} title="Open this month's records">
                    <td>{m.full}</td>
                    <td>{m.created}</td>
                    <td>{m.completed}</td>
                    <td>{m.closed}</td>
                    <td>{m.open}</td>
                    <td>{m.overdue}</td>
                    <td>{m.completion_rate}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "yearly" && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 font-semibold">Year-over-year comparison — click a row for details</div>
          <table className="data">
            <thead>
              <tr>
                <th>Year</th>
                <th>Total</th>
                <th>Open</th>
                <th>Closed</th>
                <th>Overdue</th>
                <th>Completion</th>
                <th>Avg close (d)</th>
                <th>YoY total</th>
              </tr>
            </thead>
            <tbody>
              {(yearly?.years || []).map((y) => (
                <tr key={y.year} onClick={() => go({ year: y.year })}>
                  <td className="font-semibold">{y.year}</td>
                  <td>{y.total}</td>
                  <td>{y.open}</td>
                  <td>{y.closed}</td>
                  <td>{y.overdue}</td>
                  <td>{y.completion_rate}%</td>
                  <td>{y.average_closing_days ?? "—"}</td>
                  <td>
                    {y.yoy
                      ? `${y.yoy.total.change >= 0 ? "+" : ""}${y.yoy.total.change} (${y.yoy.total.pct}%)`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "reasons" && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 font-semibold">Why are work orders still open?</div>
          <table className="data">
            <thead>
              <tr>
                <th>Reason</th>
                <th>Orders</th>
                <th>% of open</th>
              </tr>
            </thead>
            <tbody>
              {(dash?.reasons || []).map((r) => (
                <tr
                  key={r.name}
                  onClick={() => nav(`/work-orders?flag=open&reason=${encodeURIComponent(r.name)}`)}
                >
                  <td>{r.name}</td>
                  <td className="font-semibold">{r.value}</td>
                  <td>{r.pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "aging" && (
        <ChartCard title="Open work order aging" subtitle="Click a bar to view those records">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={dash?.aging || []}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar
                dataKey="value"
                fill="#F59E0B"
                isAnimationActive={false}
                cursor="pointer"
                onClick={(d) => d?.id && nav(`/work-orders?flag=open&aging=${d.id}`)}
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      )}

      {tab === "priority" && (
        <div className="card overflow-hidden">
          <table className="data">
            <thead>
              <tr>
                <th>Priority</th>
                <th>Total</th>
                <th>Open</th>
                <th>Closed</th>
                <th>Overdue</th>
                <th>Completion</th>
              </tr>
            </thead>
            <tbody>
              {(dash?.priorities || []).map((r) => (
                <tr key={r.name} onClick={() => nav(`/work-orders?priority=${encodeURIComponent(r.name)}`)}>
                  <td>{r.name}</td>
                  <td>{r.total}</td>
                  <td>{r.open}</td>
                  <td>{r.closed}</td>
                  <td>{r.overdue}</td>
                  <td>{r.completion_rate}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
