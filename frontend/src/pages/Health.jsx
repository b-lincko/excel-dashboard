import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";
import KPICard from "../components/KPICard.jsx";

const SECTIONS = [
  ["missing_id", "Missing work-order IDs", "Rows with data but a blank IM Work Order #. The normal reader skips these."],
  ["blank_assign", "Blank Assign to (open)", "Open rows with no assignee."],
  ["blank_status", "Blank STATUS", "Rows that have a WO # but no status."],
  ["overwritten_formula", "Formula columns typed over", "Configured formula columns that now hold a typed value instead of a formula."],
  ["missing_formula", "Formula columns empty", "Configured formula columns that are blank."],
  ["duplicate_id", "Duplicate WO # on a sheet", "The same IM Work Order # appears more than once on one worksheet."],
];

export default function Health() {
  const { toast, ask } = useUi();
  const { can } = useAuth();
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [similar, setSimilar] = useState(null);
  const [backups, setBackups] = useState([]);
  const [healthMap, setHealthMap] = useState({});
  const [rowRestore, setRowRestore] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const uploadRef = useRef(null);

  function load() {
    setLoading(true);
    api
      .get("/api/ops/health")
      .then(setData)
      .catch((e) => toast(e.message, "error"))
      .finally(() => setLoading(false));
    api.get("/api/ops/similar").then(setSimilar).catch(() => {});
    if (can("backup")) {
      api.get("/api/settings/backups").then((d) => setBackups(d.items || [])).catch(() => {});
    }
  }

  useEffect(load, []);

  async function uploadBackup(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const d = await api.upload("/api/settings/backups/upload", fd);
      if (d.health) setHealthMap((prev) => ({ ...prev, [d.path]: d.health }));
      toast(
        d.health && !d.health.ok
          ? `Saved as backup, but health check failed (${d.health.error || "row count mismatch"})`
          : `Backup uploaded · ${d.name}`,
        d.health && !d.health.ok ? "error" : "success"
      );
      api.get("/api/settings/backups").then((x) => setBackups(x.items || [])).catch(() => {});
    } catch (err) {
      toast(err.message || "Upload failed", "error");
    } finally {
      setUploading(false);
    }
  }

  const c = data?.counts || {};
  const issues = data?.issues || {};

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Excel health</h1>
          <p className="text-sm text-slate-500">
            Raw scan of the live workbook · {data?.scanned_rows ?? "—"} data rows on {data?.sheets ?? "—"} sheets
            {loading ? " · scanning…" : ""}
          </p>
        </div>
        <button className="btn-outline" onClick={load} disabled={loading}>
          {loading ? "Scanning…" : "Scan again"}
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <KPICard label="Missing IDs" value={c.missing_id} accent="rose" />
        <KPICard label="Blank assign" value={c.blank_assign} accent="amber" />
        <KPICard label="Blank status" value={c.blank_status} accent="amber" />
        <KPICard label="Typed-over formulas" value={c.overwritten_formula} accent="rose" />
        <KPICard label="Empty formulas" value={c.missing_formula} accent="sky" />
        <KPICard label="Duplicate WO #" value={c.duplicate_id} accent="rose" />
      </div>

      {SECTIONS.map(([key, title, hint]) => {
        const rows = issues[key] || [];
        const count = c[key] ?? rows.length;
        return (
          <div key={key} className="card overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 dark:border-white/5">
              <div className="font-semibold">
                {title} ({count})
              </div>
              <div className="text-xs text-slate-500 mt-0.5">{hint}</div>
            </div>
            <div className="table-wrap max-h-[280px]">
              <table className="data">
                <thead>
                  <tr>
                    <th>Site</th>
                    <th>Row</th>
                    <th>IM WO #</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={`${r.record_id || r.work_order_id || i}-${i}`} className="!cursor-default">
                      <td>{r.site || r.sheet || "—"}</td>
                      <td className="font-mono text-xs">{r.row || (r.rows || []).join(", ") || "—"}</td>
                      <td className="font-mono text-xs">{r.work_order_id || "—"}</td>
                      <td className="text-sm text-slate-500 truncate max-w-[360px]">
                        {r.column ? `${r.column}${r.value ? ` = ${r.value}` : ""}` : r.status || r.record_id || "—"}
                      </td>
                    </tr>
                  ))}
                  {!rows.length && (
                    <tr className="!cursor-default">
                      <td colSpan={4} className="text-center text-slate-400 py-8">
                        None found in this scan.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}

      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 dark:border-white/5">
          <div className="font-semibold">Similar open MRs ({similar?.count ?? 0})</div>
          <div className="text-xs text-slate-500 mt-0.5">Same asset (WO Asset Name) and overlapping material text. Live from Excel, not duplicate WO #s.</div>
        </div>
        <div className="table-wrap max-h-[360px]">
          <table className="data">
            <thead>
              <tr>
                <th>Asset</th>
                <th>WO A</th>
                <th>Material A</th>
                <th>WO B</th>
                <th>Material B</th>
                <th>Overlap</th>
              </tr>
            </thead>
            <tbody>
              {(similar?.items || []).map((p, i) => (
                <tr key={`${p.a?.record_id}-${p.b?.record_id}-${i}`} className="!cursor-default">
                  <td className="text-sm">{p.asset || "—"}</td>
                  <td>
                    <button className="font-mono text-xs font-semibold text-brand-700 hover:underline" onClick={() => nav(`/work-orders/${encodeURIComponent(p.a?.record_id || p.a?.work_order_id)}`)}>
                      {p.a?.work_order_id}
                    </button>
                  </td>
                  <td className="max-w-[200px] truncate text-sm">{p.a?.description}</td>
                  <td>
                    <button className="font-mono text-xs font-semibold text-brand-700 hover:underline" onClick={() => nav(`/work-orders/${encodeURIComponent(p.b?.record_id || p.b?.work_order_id)}`)}>
                      {p.b?.work_order_id}
                    </button>
                  </td>
                  <td className="max-w-[200px] truncate text-sm">{p.b?.description}</td>
                  <td>{p.score}</td>
                </tr>
              ))}
              {!(similar?.items || []).length && (
                <tr className="!cursor-default">
                  <td colSpan={6} className="text-center text-slate-400 py-8">
                    No similar open pairs on the same asset.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {can("backup") && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 dark:border-white/5 flex items-center justify-between gap-3">
            <div>
              <div className="font-semibold">Backup restore</div>
              <div className="text-xs text-slate-500 mt-0.5">Upload an older workbook into the backup folder without replacing live Excel. Then check, restore the file, or restore one row. Current workbook is copied aside first on restore.</div>
            </div>
            <div className="flex gap-2">
              <input
                ref={uploadRef}
                type="file"
                accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                className="hidden"
                onChange={uploadBackup}
              />
              <button className="btn-outline text-xs" type="button" onClick={() => uploadRef.current?.click()} disabled={uploading}>
                {uploading ? "Uploading…" : "Upload backup"}
              </button>
              <button className="btn-outline text-xs" onClick={() => nav("/settings")}>
                Backup settings
              </button>
            </div>
          </div>
          <table className="data">
            <thead>
              <tr>
                <th>File</th>
                <th>Kind</th>
                <th>Modified</th>
                <th>Health</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {backups.slice(0, 8).map((b) => {
                const h = healthMap[b.path];
                return (
                  <tr key={b.path} className="!cursor-default">
                    <td className="font-mono text-xs">{b.name}</td>
                    <td className="uppercase text-[11px] text-slate-500">{b.reason || "—"}</td>
                    <td>{b.modified}</td>
                    <td className="text-xs">
                      {h ? (h.ok ? `${h.backup_count} rows (live ${h.live_count})` : h.error || "Bad copy") : "—"}
                    </td>
                    <td>
                      <div className="flex gap-1 justify-end">
                        <button
                          className="btn-outline !py-1 !px-2 text-xs"
                          onClick={async () => {
                            try {
                              const d = await api.post("/api/settings/backups/check", { path: b.path });
                              setHealthMap((prev) => ({ ...prev, [b.path]: d }));
                              toast(d.ok ? "Backup looks healthy" : "Backup does not match live row counts", d.ok ? "success" : "error");
                            } catch (e) {
                              toast(e.message, "error");
                            }
                          }}
                        >
                          Check
                        </button>
                        <button
                          className="btn-outline !py-1 !px-2 text-xs"
                          onClick={async () => {
                            const ok = await ask({
                              title: "Restore this backup?",
                              body: `${b.name}\nThe current workbook will be copied aside first.`,
                              confirmLabel: "Restore file",
                              danger: true,
                            });
                            if (!ok) return;
                            await api.post("/api/settings/backups/restore", { path: b.path });
                            toast("Backup restored", "success");
                            window.dispatchEvent(new CustomEvent("woms:data"));
                            load();
                          }}
                        >
                          Restore file
                        </button>
                        <button className="btn-outline !py-1 !px-2 text-xs" onClick={() => setRowRestore({ path: b.path, name: b.name, record_id: "", work_order_id: "", site: "", preview: null, busy: false })}>
                          Restore row
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {!backups.length && (
                <tr className="!cursor-default">
                  <td colSpan={5} className="text-center text-slate-400 py-8">
                    No backups yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {rowRestore && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={() => setRowRestore(null)}>
          <div className="card w-full max-w-lg p-4 space-y-3" onClick={(e) => e.stopPropagation()}>
            <div className="font-semibold">Restore one row from {rowRestore.name}</div>
            <div>
              <label className="lbl">Record id</label>
              <input value={rowRestore.record_id} onChange={(e) => setRowRestore({ ...rowRestore, record_id: e.target.value })} placeholder="SH5-SH1:12" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="lbl">IM WO #</label>
                <input value={rowRestore.work_order_id} onChange={(e) => setRowRestore({ ...rowRestore, work_order_id: e.target.value })} />
              </div>
              <div>
                <label className="lbl">Site</label>
                <input value={rowRestore.site} onChange={(e) => setRowRestore({ ...rowRestore, site: e.target.value })} />
              </div>
            </div>
            {rowRestore.preview && (
              <div className="max-h-40 overflow-auto text-sm">
                {!(rowRestore.preview.diffs || []).length ? (
                  <div className="text-slate-500">No mapped field differences.</div>
                ) : (
                  (rowRestore.preview.diffs || []).map((d) => (
                    <div key={d.field} className="flex gap-2 border-b border-slate-100 dark:border-white/5 py-1">
                      <span className="font-medium">{d.field}</span>
                      <span className="text-slate-500 truncate">{d.current || "—"}</span>
                      <span className="truncate">{d.backup || "—"}</span>
                    </div>
                  ))
                )}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button className="btn-ghost" type="button" onClick={() => setRowRestore(null)}>
                Cancel
              </button>
              <button
                className="btn-outline"
                type="button"
                disabled={rowRestore.busy || !(rowRestore.record_id || rowRestore.work_order_id)}
                onClick={async () => {
                  setRowRestore({ ...rowRestore, busy: true });
                  try {
                    const d = await api.post("/api/settings/backups/preview-row", {
                      path: rowRestore.path,
                      record_id: rowRestore.record_id,
                      work_order_id: rowRestore.work_order_id,
                      site: rowRestore.site,
                    });
                    setRowRestore((prev) => ({ ...prev, preview: d, busy: false }));
                  } catch (e) {
                    toast(e.message, "error");
                    setRowRestore((prev) => ({ ...prev, busy: false }));
                  }
                }}
              >
                Preview
              </button>
              <button
                className="btn-primary"
                type="button"
                disabled={rowRestore.busy || !rowRestore.preview?.matched_live}
                onClick={async () => {
                  setRowRestore({ ...rowRestore, busy: true });
                  try {
                    const d = await api.post("/api/settings/backups/restore-row", {
                      path: rowRestore.path,
                      record_id: rowRestore.record_id,
                      work_order_id: rowRestore.work_order_id,
                      site: rowRestore.site,
                    });
                    toast(d.unchanged ? "Row already matches the backup" : "Row restored from backup", "success");
                    setRowRestore(null);
                    window.dispatchEvent(new CustomEvent("woms:data"));
                    load();
                  } catch (e) {
                    toast(e.message, "error");
                    setRowRestore((prev) => ({ ...prev, busy: false }));
                  }
                }}
              >
                Restore row
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
