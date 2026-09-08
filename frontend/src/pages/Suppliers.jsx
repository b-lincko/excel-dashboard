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
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";
import KPICard from "../components/KPICard.jsx";
import ChartCard from "../components/ChartCard.jsx";
import OpsTable from "../components/OpsTable.jsx";
import Filters from "../components/Filters.jsx";

const PIE = ["#0F3D5E", "#1D6A96", "#0EA5E9", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#64748B"];
const TABS = [
  ["scorecard", "Scorecard"],
  ["board", "PO board"],
  ["lists", "Lists"],
  ["cards", "Supplier cards"],
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
  const [card, setCard] = useState(null);
  const [cardBusy, setCardBusy] = useState(false);
  const { can } = useAuth();
  const { toast } = useUi();

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
          Supplier, PO, RFQ date, ETA and delivery status · {data?.as_of || "—"}
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
            <ChartCard title="On-time rate by supplier" subtitle="Delivered/closed vs due date">
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
            <ChartCard title="Delivery status" subtitle="Live delivery status values">
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

      {tab === "cards" && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 dark:border-white/5">
            <div className="font-semibold">Supplier cards</div>
            <p className="text-xs text-slate-500">Phone, contact, lead time and notes live in the catalog. On-time % is counted from live records.</p>
          </div>
          <div className="table-wrap max-h-[560px]">
            <table className="data">
              <thead>
                <tr>
                  <th>Supplier</th>
                  <th>On-time</th>
                  <th>Open</th>
                  <th>Contact</th>
                  <th>Phone</th>
                  <th>Lead (days)</th>
                  <th>Notes</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {(data?.suppliers || [])
                  .filter((r) => r.name !== "Unassigned")
                  .map((r) => (
                    <tr key={r.name} className="!cursor-default">
                      <td className="font-medium">{r.name}</td>
                      <td>{r.scored ? `${r.on_time_rate}%` : "—"}</td>
                      <td>{r.open}</td>
                      <td>{r.contact || "—"}</td>
                      <td>{r.phone || "—"}</td>
                      <td>{r.lead_time_days ?? "—"}</td>
                      <td className="max-w-[220px] truncate">{r.notes || "—"}</td>
                      <td>
                        {can("edit") && (
                          <button className="btn-outline !py-1 !px-2 text-xs" onClick={() => setCard({ ...r })}>
                            Edit card
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {card && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={() => setCard(null)}>
          <div className="card w-full max-w-lg p-4 space-y-3" onClick={(e) => e.stopPropagation()}>
            <div className="font-semibold">{card.name}</div>
            <p className="text-xs text-slate-500">On-time {card.scored ? `${card.on_time_rate}%` : "—"} from live records. Card fields stay with the catalog.</p>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="lbl">Contact</label>
                <input value={card.contact || ""} onChange={(e) => setCard({ ...card, contact: e.target.value })} />
              </div>
              <div>
                <label className="lbl">Phone</label>
                <input value={card.phone || ""} onChange={(e) => setCard({ ...card, phone: e.target.value })} />
              </div>
              <div>
                <label className="lbl">Email</label>
                <input value={card.email || ""} onChange={(e) => setCard({ ...card, email: e.target.value })} />
              </div>
              <div>
                <label className="lbl">Lead time (days)</label>
                <input type="number" value={card.lead_time_days ?? ""} onChange={(e) => setCard({ ...card, lead_time_days: e.target.value === "" ? "" : Number(e.target.value) })} />
              </div>
              <div className="col-span-2">
                <label className="lbl">Notes</label>
                <textarea rows={3} value={card.notes || ""} onChange={(e) => setCard({ ...card, notes: e.target.value })} />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button className="btn-ghost" type="button" onClick={() => setCard(null)}>
                Cancel
              </button>
              <button
                className="btn-primary"
                type="button"
                disabled={cardBusy}
                onClick={async () => {
                  setCardBusy(true);
                  try {
                    let id = card.id;
                    if (!id) {
                      const created = await api.post("/api/catalog/suppliers", { name: card.name });
                      id = created.item?.id;
                    }
                    const d = await api.put(`/api/catalog/suppliers/${id}`, {
                      phone: card.phone || "",
                      email: card.email || "",
                      contact: card.contact || "",
                      lead_time_days: card.lead_time_days === "" ? null : card.lead_time_days,
                      notes: card.notes || "",
                    });
                    setData((prev) => {
                      if (!prev?.suppliers) return prev;
                      return {
                        ...prev,
                        suppliers: prev.suppliers.map((r) => (r.name === card.name ? { ...r, ...d.item } : r)),
                      };
                    });
                    toast("Supplier card saved", "success");
                    setCard(null);
                  } catch (e) {
                    toast(e.message, "error");
                  } finally {
                    setCardBusy(false);
                  }
                }}
              >
                Save card
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
