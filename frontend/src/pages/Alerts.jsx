import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, CalendarClock } from "lucide-react";
import { api, qs } from "../lib/api.js";
import { goSearch, useLiveReload } from "../lib/live.js";
import KPICard from "../components/KPICard.jsx";
import Filters from "../components/Filters.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

export default function Alerts() {
  const nav = useNavigate();
  const tick = useLiveReload();
  const [filters, setFilters] = useState({});
  const [options, setOptions] = useState({});
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/api/work-orders/options").then((d) => setOptions(d.options || {})).catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!data) setLoading(true);
    api
      .get(`/api/ops/alerts${qs(filters)}`)
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

  const go = (params) => goSearch(nav, { ...filters, ...params });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">SLA / due-date alerts</h1>
        <p className="text-sm text-slate-500">
          Open MRs due today through {data?.window_days ?? 3} days · {data?.as_of || "—"} · live from Excel
          {loading ? " · updating…" : ""}
        </p>
      </div>
      <Filters value={filters} onChange={setFilters} options={options} />
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-3">
        <KPICard label="Due soon" value={data?.count ?? "—"} icon={Bell} accent="amber" onClick={() => go({ flag: "due_soon" })} hint={`Next ${data?.window_days ?? 3} days`} />
        {(data?.buckets || []).map((b) => (
          <KPICard
            key={b.days}
            label={b.label}
            value={b.count}
            icon={CalendarClock}
            accent={b.days === 0 ? "rose" : "sky"}
            onClick={() => go({ flag: "due_soon" })}
          />
        ))}
      </div>
      {(data?.sites || []).map((site) => (
        <div key={site.name} className="card overflow-hidden">
          <div className="px-4 py-3 flex items-center justify-between gap-3 border-b border-slate-100 dark:border-white/5">
            <div>
              <div className="font-semibold">{site.name}</div>
              <div className="text-xs text-slate-500">{site.count} due soon</div>
            </div>
            <button className="btn-outline !py-1 text-xs" onClick={() => go({ flag: "due_soon", department: site.name })}>
              View site
            </button>
          </div>
          {site.assignees.map((person) => (
            <div key={person.name} className="border-t border-slate-100 dark:border-white/5">
              <div className="px-4 py-2 text-xs uppercase tracking-wider text-slate-500 flex items-center justify-between">
                <span>
                  {person.name} · {person.count}
                </span>
                <button className="text-brand-700 dark:text-cyan-300 hover:underline normal-case tracking-normal" onClick={() => go({ flag: "due_soon", department: site.name, assigned_to: person.name })}>
                  Open list
                </button>
              </div>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>IM WO #</th>
                      <th>Material</th>
                      <th>Due</th>
                      <th>Days left</th>
                      <th>Status</th>
                      <th>Priority</th>
                    </tr>
                  </thead>
                  <tbody>
                    {person.items.map((r) => (
                      <tr key={r.record_id} onClick={() => nav(`/work-orders/${encodeURIComponent(r.record_id || r.work_order_id)}`)}>
                        <td className="font-mono text-xs font-semibold">{r.work_order_id}</td>
                        <td className="max-w-[280px] truncate">{r.description || "—"}</td>
                        <td>{(r.due_date || "").slice(0, 10)}</td>
                        <td>{r.days_until_due === 0 ? "Today" : r.days_until_due}</td>
                        <td>
                          <StatusBadge value={r.status} />
                        </td>
                        <td>
                          <StatusBadge value={r.priority} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      ))}
      {!loading && !data?.count && <div className="card p-8 text-center text-sm text-slate-500">No material requests are due in the next {data?.window_days ?? 3} days.</div>}
    </div>
  );
}
