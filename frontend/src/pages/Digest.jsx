import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Ban, Bell, Printer } from "lucide-react";
import { api, qs } from "../lib/api.js";
import { useApiData, useOptionsCache } from "../lib/apiCache.js";
import { goSearch, useLiveReload } from "../lib/live.js";
import KPICard from "../components/KPICard.jsx";
import Filters from "../components/Filters.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

export default function Digest() {
  const nav = useNavigate();
  const tick = useLiveReload();
  const [filters, setFilters] = useState({});
  const [options, setOptions] = useState({});
  const { data, setData, loading } = useApiData(
    `digest:${qs(filters)}`,
    `/api/ops/digest${qs(filters)}`,
    [filters, tick]
  );

  const cachedOptions = useOptionsCache();
  useEffect(() => {
    if (cachedOptions) setOptions(cachedOptions);
  }, [cachedOptions]);



  const c = data?.counts || {};
  const go = (params) => goSearch(nav, { ...filters, ...params });

  return (
    <div className="space-y-5 briefing">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Morning digest</h1>
          <p className="text-sm text-slate-500">
            Overdue, UNDER NTP and due soon · grouped by site then assignee · {data?.as_of || "—"}
            {loading ? " · updating…" : ""}
          </p>
        </div>
        <div className="flex gap-2 no-print">
          <button className="btn-outline" onClick={() => api.download(`/api/ops/digest?fmt=pdf${qs(filters).replace("?", "&")}`, "morning_digest.pdf")}>
            PDF
          </button>
          <button className="btn-primary" onClick={() => window.print()}>
            <Printer size={14} /> Print
          </button>
        </div>
      </div>

      <div className="print-only text-xs text-slate-500">
        Linkco MR morning digest · printed {new Date().toLocaleString()} · overdue {c.overdue ?? 0} · NTP {c.ntp ?? 0} · due soon {c.due_soon ?? 0}
      </div>

      <div className="no-print">
        <Filters value={filters} onChange={setFilters} options={options} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <KPICard label="Overdue" value={c.overdue} icon={AlertTriangle} accent="rose" onClick={() => go({ flag: "overdue" })} />
        <KPICard label="UNDER NTP" value={c.ntp} icon={Ban} accent="amber" onClick={() => go({ flag: "ntp" })} />
        <KPICard label="Due soon" value={c.due_soon} icon={Bell} accent="sky" onClick={() => go({ flag: "due_soon" })} />
      </div>

      {(data?.sections || []).map((section) => (
        <div key={section.id} className="space-y-3 print-break">
          <h2 className="text-lg font-semibold">
            {section.title} ({section.count})
          </h2>
          {(section.sites || []).map((site) => (
            <div key={`${section.id}-${site.name}`} className="card overflow-hidden">
              <div className="px-4 py-3 flex items-center justify-between gap-3 border-b border-slate-100 dark:border-white/5">
                <div>
                  <div className="font-semibold">{site.name}</div>
                  <div className="text-xs text-slate-500">{site.count} in this list</div>
                </div>
                <button className="btn-outline !py-1 text-xs no-print" onClick={() => go({ flag: section.id === "ntp" ? "ntp" : section.id, department: site.name })}>
                  View site
                </button>
              </div>
              {(site.assignees || []).map((person) => (
                <div key={person.name} className="border-t border-slate-100 dark:border-white/5">
                  <div className="px-4 py-2 text-xs uppercase tracking-wider text-slate-500">
                    {person.name} · {person.count}
                  </div>
                  <div className="table-wrap">
                    <table className="data">
                      <thead>
                        <tr>
                          <th>MR #</th>
                          <th>Material</th>
                          <th>Due</th>
                          <th>Status</th>
                          <th>Assigned</th>
                          <th>Justification</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(person.items || []).map((r) => (
                          <tr key={r.record_id} onClick={() => nav(`/work-orders/${encodeURIComponent(r.record_id || r.work_order_id)}`)}>
                            <td className="font-mono text-xs font-semibold">{r.work_order_id}</td>
                            <td className="max-w-[280px] truncate">{r.description || "—"}</td>
                            <td>{(r.due_date || "").slice(0, 10) || "—"}</td>
                            <td>
                              <StatusBadge value={r.status} />
                            </td>
                            <td>{r.assigned_to || person.name}</td>
                            <td className="max-w-[200px] truncate" title={r.delay_justification || r.delay_reason || r.issue || ""}>
                              {r.delay_justification || r.delay_reason || r.issue || "—"}
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
          {!section.count && <div className="card p-6 text-center text-sm text-slate-500">None.</div>}
        </div>
      ))}
    </div>
  );
}
