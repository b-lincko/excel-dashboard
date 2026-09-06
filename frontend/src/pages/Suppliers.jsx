import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Ban, Clock, Package, Send, Truck } from "lucide-react";
import { api, qs } from "../lib/api.js";
import { goSearch, useLiveReload } from "../lib/live.js";
import KPICard from "../components/KPICard.jsx";
import ChartCard from "../components/ChartCard.jsx";
import OpsTable from "../components/OpsTable.jsx";
import Filters from "../components/Filters.jsx";

const PIE = ["#0F3D5E", "#1D6A96", "#0EA5E9", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#64748B"];
const TABS = [
  ["scorecard", "Scorecard"],
  ["board", "PO board"],
  ["lists", "Lists"],
];
const BOARD = [
  ["need_rfq", "Need RFQ", "Open, no PO, RFQ date empty", "need_rfq", "bg-slate-50 dark:bg-white/5"],
  ["rfq_sent", "RFQ sent", "RFQ / expected PO date filled, still no PO #", "rfq_sent", "bg-sky-50 dark:bg-sky-500/10"],
  ["po_issued", "PO issued", "PO number filled, not delivered, ETA ok", "po_issued", "bg-indigo-50 dark:bg-indigo-500/10"],
  ["eta_late", "ETA missed", "ETA before today and not delivered", "eta_late", "bg-rose-50 dark:bg-rose-500/10"],
  ["delivered", "Delivered", "Delivery Status = Delivered", "delivered", "bg-emerald-50 dark:bg-emerald-500/10"],
];

export default function Suppliers() {
  const nav = useNavigate();
  const tick = useLiveReload();
  const [filters, setFilters] = useState({});
  const [options, setOptions] = useState({});
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("scorecard");

  useEffect(() => {
    api.get("/api/work-orders/options").then((d) => setOptions(d.options || {})).catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!data) setLoading(true);
    api
      .get(`/api/ops/suppliers${qs(filters)}`)
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

  const k = data?.kpis || {};
  const go = (params) => goSearch(nav, { ...filters, ...params });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Suppliers & POs</h1>
        <p className="text-sm text-slate-500">
          Live from Excel (Supplier Name, PO NO #, RFQ/PO date, ETA, Delivery Status, delay source) · {data?.as_of || "—"}
          {loading ? " · updating…" : ""}
        </p>
      </div>

      <Filters value={filters} onChange={setFilters} options={options} />

      <div className="flex flex-wrap gap-2">
        {TABS.map(([id, label]) => (
          <button key={id} className={tab === id ? "btn-primary" : "btn-outline"} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <KPICard label="On-time" value={k.on_time_rate != null ? `${k.on_time_rate}%` : "—"} icon={Package} accent="emerald" hint={`${k.on_time ?? 0} of ${k.scored ?? 0} scored`} />
        <KPICard label="Need RFQ" value={k.need_rfq} icon={Clock} accent="slate" hint="No PO, no RFQ date" onClick={() => go({ flag: "need_rfq" })} />
        <KPICard label="RFQ sent" value={k.rfq_sent} icon={Send} accent="sky" hint="RFQ date, waiting on PO" onClick={() => go({ flag: "rfq_sent" })} />
        <KPICard label="PO issued" value={k.po_issued} icon={Truck} accent="indigo" hint="Has PO #, ETA ok" onClick={() => go({ flag: "po_issued" })} />
        <KPICard label="ETA missed" value={k.eta_late} icon={Ban} accent="rose" hint="ETA before today" onClick={() => go({ flag: "eta_late" })} />
        <KPICard label="Delivered" value={k.delivered} icon={Package} accent="emerald" onClick={() => go({ flag: "delivered" })} />
      </div>

      {tab === "scorecard" && (
        <div className="space-y-4">
          <div className="grid lg:grid-cols-2 gap-4">
            <ChartCard title="On-time rate by supplier" subtitle="Delivered/closed vs due date from Excel">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data?.on_time || []}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" interval={0} angle={-25} textAnchor="end" height={70} tick={{ fontSize: 11 }} />
                  <YAxis domain={[0, 100]} />
                  <Tooltip />
                  <Bar
                    dataKey="on_time_rate"
                    fill="#10B981"
                    isAnimationActive={false}
                    cursor="pointer"
                    onClick={(d) => d?.name && go({ supplier: d.name })}
                  />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
            <ChartCard title="Delay source" subtitle="Site / procurement / supplier notes on pending MRs">
              {(data?.delays || []).length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.delays}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" interval={0} angle={-25} textAnchor="end" height={70} tick={{ fontSize: 11 }} />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="site" stackId="a" fill="#0EA5E9" isAnimationActive={false} />
                    <Bar dataKey="procurement" stackId="a" fill="#F59E0B" isAnimationActive={false} />
                    <Bar dataKey="supplier" stackId="a" fill="#EF4444" isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full grid place-items-center text-sm text-slate-500">No delay-source notes in the current filter.</div>
              )}
            </ChartCard>
          </div>
          <div className="grid lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 card overflow-hidden">
              <div className="px-4 py-3 font-semibold border-b border-slate-100 dark:border-white/5">Supplier scorecard</div>
              <div className="table-wrap max-h-[480px]">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Supplier</th>
                      <th>Total</th>
                      <th>Open</th>
                      <th>On-time</th>
                      <th>Overdue</th>
                      <th>Need RFQ</th>
                      <th>PO issued</th>
                      <th>ETA late</th>
                      <th>Site</th>
                      <th>Proc.</th>
                      <th>Supplier delay</th>
                      <th>Avg age</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data?.suppliers || []).map((r) => (
                      <tr key={r.name} onClick={() => go({ supplier: r.name === "Unassigned" ? "" : r.name })}>
                        <td className="font-medium">{r.name}</td>
                        <td>{r.total}</td>
                        <td>{r.open}</td>
                        <td>{r.scored ? `${r.on_time_rate}%` : "—"}</td>
                        <td className={r.overdue ? "text-rose-600 font-semibold" : ""}>{r.overdue}</td>
                        <td>{r.need_rfq}</td>
                        <td>{r.po_issued}</td>
                        <td className={r.eta_late ? "text-rose-600 font-semibold" : ""}>{r.eta_late}</td>
                        <td>{r.delay_site}</td>
                        <td>{r.delay_procurement}</td>
                        <td>{r.delay_supplier}</td>
                        <td>{r.avg_aging_days ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <ChartCard title="Delivery status" subtitle="Excel Delivery Status values">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data?.delivery || []}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={48}
                    outerRadius={78}
                    isAnimationActive={false}
                    onClick={(d) => d?.name && go({ delay_reason: d.name })}
                  >
                    {(data?.delivery || []).map((_, i) => (
                      <Cell key={i} fill={PIE[i % PIE.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>
        </div>
      )}

      {tab === "board" && (
        <div className="grid md:grid-cols-2 xl:grid-cols-5 gap-3">
          {BOARD.map(([key, title, hint, flag, tone]) => (
            <div key={key} className={`card overflow-hidden ${tone}`}>
              <button type="button" className="w-full text-left px-3 py-3 border-b border-slate-200/70 dark:border-white/10" onClick={() => go({ flag })}>
                <div className="flex items-baseline justify-between gap-2">
                  <div className="font-semibold">{title}</div>
                  <div className="text-lg font-bold">{data?.board_counts?.[key] ?? 0}</div>
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">{hint}</div>
              </button>
              <ul className="max-h-[520px] overflow-y-auto divide-y divide-slate-100 dark:divide-white/5">
                {(data?.board?.[key] || []).map((r) => (
                  <li key={r.record_id}>
                    <button
                      type="button"
                      className="w-full text-left px-3 py-2.5 hover:bg-white/60 dark:hover:bg-white/5"
                      onClick={() => nav(`/work-orders/${encodeURIComponent(r.record_id || r.work_order_id)}`)}
                    >
                      <div className="font-mono text-xs font-semibold">{r.work_order_id}</div>
                      <div className="text-sm truncate">{r.description || r.location || "—"}</div>
                      <div className="text-[11px] text-slate-500 truncate">
                        {r.supplier || "No supplier"} · {r.po_number || "no PO"} · age {r.aging_days ?? "—"}
                      </div>
                    </button>
                  </li>
                ))}
                {!(data?.board?.[key] || []).length && <li className="px-3 py-8 text-center text-sm text-slate-400">Empty</li>}
              </ul>
            </div>
          ))}
        </div>
      )}

      {tab === "lists" && (
        <>
          <OpsTable
            title={`Need RFQ (${k.need_rfq ?? 0})`}
            subtitle="Open, no PO number, RFQ / expected PO date empty"
            rows={data?.need_rfq || []}
            columns={[
              ["work_order_id", "IM WO #"],
              ["description", "Material"],
              ["assigned_to", "Assigned"],
              ["work_type", "Purchase type"],
              ["status", "Status"],
              ["aging_days", "Age"],
            ]}
            viewAll={() => go({ flag: "need_rfq" })}
          />
          <OpsTable
            title={`RFQ sent (${k.rfq_sent ?? 0})`}
            subtitle="RFQ / expected PO date is filled, still waiting for a PO number"
            rows={data?.rfq_sent || []}
            columns={[
              ["work_order_id", "IM WO #"],
              ["supplier", "Supplier"],
              ["scheduled_date", "RFQ / PO date"],
              ["description", "Material"],
              ["assigned_to", "Assigned"],
              ["aging_days", "Age"],
            ]}
            viewAll={() => go({ flag: "rfq_sent" })}
          />
          <OpsTable
            title={`PO issued (${k.po_issued ?? 0})`}
            subtitle="PO number filled, not delivered, ETA not missed"
            rows={data?.po_issued || data?.pending_pos || []}
            columns={[
              ["work_order_id", "IM WO #"],
              ["supplier", "Supplier"],
              ["po_number", "PO"],
              ["description", "Material"],
              ["closed_date", "ETA"],
              ["issue", "Delivery"],
              ["status", "Status"],
              ["aging_days", "Age"],
            ]}
            viewAll={() => go({ flag: "po_issued" })}
          />
          <OpsTable
            title={`ETA missed (${k.eta_late ?? 0})`}
            subtitle="ETA / expected RFQ date is before today and not delivered"
            rows={data?.eta_late || []}
            columns={[
              ["work_order_id", "IM WO #"],
              ["supplier", "Supplier"],
              ["po_number", "PO"],
              ["closed_date", "ETA"],
              ["days_to_eta", "Days vs ETA"],
              ["issue", "Delivery"],
              ["assigned_to", "Assigned"],
            ]}
            viewAll={() => go({ flag: "eta_late" })}
          />
        </>
      )}
    </div>
  );
}
