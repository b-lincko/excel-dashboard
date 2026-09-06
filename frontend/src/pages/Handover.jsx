import { useEffect, useState } from "react";
import { Printer } from "lucide-react";
import { api, qs } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";
import { useLiveReload } from "../lib/live.js";
import KPICard from "../components/KPICard.jsx";
import OpsTable from "../components/OpsTable.jsx";
import Filters from "../components/Filters.jsx";

const BUCKETS = [
  ["still_open", "Still OPEN", "STATUS is OPEN"],
  ["waiting_ntp", "Waiting on NTP", "UNDER NTP — still outstanding"],
  ["waiting_supplier", "Waiting on supplier", "Open, with a supplier, not delivered"],
];

export default function Handover() {
  const { can } = useAuth();
  const { toast } = useUi();
  const tick = useLiveReload();
  const [filters, setFilters] = useState({});
  const [options, setOptions] = useState({});
  const [data, setData] = useState(null);
  const [notes, setNotes] = useState("");
  const [shift, setShift] = useState("");
  const [department, setDepartment] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/api/work-orders/options").then((d) => setOptions(d.options || {})).catch(() => {});
  }, []);

  useEffect(() => {
    api
      .get(`/api/ops/handover${qs(filters)}`)
      .then(setData)
      .catch((e) => toast(e.message, "error"));
  }, [filters, tick]);

  const live = data?.live || {};
  const c = live.counts || {};

  async function publish() {
    setBusy(true);
    try {
      const d = await api.post("/api/ops/handover", { notes, shift, department });
      setNotes("");
      setData((prev) => ({ ...(prev || {}), items: [d.item, ...(prev?.items || [])] }));
      toast("Handover note saved", "success");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5 briefing">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Shift handover</h1>
          <p className="text-sm text-slate-500">
            Live snapshot from Excel · {live.as_of || "—"} · notes are stored in the app, not the workbook
          </p>
        </div>
        <button className="btn-primary no-print" onClick={() => window.print()}>
          <Printer size={14} /> Print
        </button>
      </div>

      <div className="no-print">
        <Filters value={filters} onChange={setFilters} options={options} />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <KPICard label="Still OPEN" value={c.still_open} accent="amber" />
        <KPICard label="Waiting on NTP" value={c.waiting_ntp} accent="rose" />
        <KPICard label="Waiting on supplier" value={c.waiting_supplier} accent="sky" />
      </div>

      {BUCKETS.map(([key, title, hint]) => (
        <OpsTable key={key} title={`${title} (${c[key] ?? 0})`} subtitle={hint} rows={live[key] || []} />
      ))}

      {can("edit") && (
        <div className="card p-5 space-y-3 no-print">
          <div className="font-semibold">Publish this snapshot</div>
          <p className="text-xs text-slate-500">
            Saves the three lists as they stand now, plus your briefing notes. Later shifts can read the frozen copy.
          </p>
          <div className="grid md:grid-cols-2 gap-3">
            <div>
              <label className="lbl">Shift</label>
              <input value={shift} onChange={(e) => setShift(e.target.value)} placeholder="Day / night / 06:00–18:00" />
            </div>
            <div>
              <label className="lbl">Site / desk</label>
              <input value={department} onChange={(e) => setDepartment(e.target.value)} placeholder="SH5-SH1, procurement…" />
            </div>
            <div className="md:col-span-2">
              <label className="lbl">Notes</label>
              <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="What the next person should pick up…" />
            </div>
          </div>
          <button className="btn-primary" onClick={publish} disabled={busy}>
            {busy ? "Saving…" : "Save handover"}
          </button>
        </div>
      )}

      <div className="card overflow-hidden">
        <div className="px-4 py-3 font-semibold">Previous handovers</div>
        <table className="data">
          <thead>
            <tr>
              <th>When</th>
              <th>By</th>
              <th>Shift</th>
              <th>OPEN</th>
              <th>NTP</th>
              <th>Supplier</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {(data?.items || []).map((h) => {
              const snap = h.snapshot || {};
              const counts = snap.counts || {};
              return (
                <tr key={h.id} className="!cursor-default">
                  <td className="font-mono text-xs">{h.created_at}</td>
                  <td>{h.username}</td>
                  <td>{h.shift || "—"}</td>
                  <td>{counts.still_open ?? "—"}</td>
                  <td>{counts.waiting_ntp ?? "—"}</td>
                  <td>{counts.waiting_supplier ?? "—"}</td>
                  <td className="max-w-[320px] truncate">{h.notes || "—"}</td>
                </tr>
              );
            })}
            {!(data?.items || []).length && (
              <tr className="!cursor-default">
                <td colSpan={7} className="text-center text-slate-400 py-8">
                  No handover notes yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
