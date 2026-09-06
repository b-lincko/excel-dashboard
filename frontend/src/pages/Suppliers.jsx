import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Ban, Clock, Package, Truck } from "lucide-react";
import { api, qs } from "../lib/api.js";
import { goSearch, useLiveReload } from "../lib/live.js";
import KPICard from "../components/KPICard.jsx";
import ChartCard from "../components/ChartCard.jsx";
import OpsTable from "../components/OpsTable.jsx";
import Filters from "../components/Filters.jsx";

const PIE = ["#0F3D5E", "#1D6A96", "#0EA5E9", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#64748B"];

export default function Suppliers() {
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
          From Supplier Name, PO NO #, ETA and Delivery Status in Excel · {data?.as_of || "—"}
          {loading ? " · updating…" : ""}
        </p>
      </div>

      <Filters value={filters} onChange={setFilters} options={options} />

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
        <KPICard label="Suppliers" value={k.suppliers} icon={Package} accent="brand" hint={`${k.unassigned ?? 0} rows with no supplier`} />
        <KPICard label="Pending POs" value={k.pending_po} icon={Truck} accent="sky" hint="Has PO #, not delivered" onClick={() => go({ flag: "pending_po" })} />
        <KPICard label="Awaiting PO" value={k.awaiting_po} icon={Clock} accent="amber" hint="Open, no PO number" onClick={() => go({ flag: "awaiting_po" })} />
        <KPICard label="ETA missed" value={k.eta_late} icon={Ban} accent="rose" hint="ETA before today" onClick={() => go({ flag: "eta_late" })} />
        <KPICard label="Delivered" value={k.delivered} icon={Package} accent="emerald" onClick={() => go({ flag: "delivered" })} />
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 card overflow-hidden">
          <div className="px-4 py-3 font-semibold border-b border-slate-100 dark:border-white/5">Supplier performance</div>
          <div className="table-wrap max-h-[420px]">
            <table className="data">
              <thead>
                <tr>
                  <th>Supplier</th>
                  <th>Total</th>
                  <th>Open</th>
                  <th>Closed</th>
                  <th>Overdue</th>
                  <th>Pending PO</th>
                  <th>ETA late</th>
                  <th>Avg age</th>
                  <th>%</th>
                </tr>
              </thead>
              <tbody>
                {(data?.suppliers || []).map((r) => (
                  <tr key={r.name} onClick={() => go({ supplier: r.name === "Unassigned" ? "" : r.name, flag: "open" })}>
                    <td className="font-medium">{r.name}</td>
                    <td>{r.total}</td>
                    <td>{r.open}</td>
                    <td>{r.closed}</td>
                    <td className={r.overdue ? "text-rose-600 font-semibold" : ""}>{r.overdue}</td>
                    <td>{r.pending_po}</td>
                    <td className={r.eta_late ? "text-rose-600 font-semibold" : ""}>{r.eta_late}</td>
                    <td>{r.avg_aging_days ?? "—"}</td>
                    <td>{r.completion_rate}%</td>
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

      <OpsTable
        title={`Pending POs (${k.pending_po ?? 0})`}
        subtitle="PO number is filled, still open, not Delivered"
        rows={data?.pending_pos || []}
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
        viewAll={() => go({ flag: "pending_po" })}
      />
      <OpsTable
        title={`Awaiting PO (${k.awaiting_po ?? 0})`}
        subtitle="Open MRs with no PO number yet"
        rows={data?.awaiting_po || []}
        columns={[
          ["work_order_id", "IM WO #"],
          ["description", "Material"],
          ["assigned_to", "Assigned"],
          ["status", "Status"],
          ["work_type", "Purchase type"],
          ["aging_days", "Age"],
        ]}
        viewAll={() => go({ flag: "awaiting_po" })}
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
    </div>
  );
}
