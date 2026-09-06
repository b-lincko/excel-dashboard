import { useEffect, useState } from "react";
import { CalendarClock, FolderOpen, HardDrive } from "lucide-react";
import { api } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";

const DAYS = [
  { id: 0, label: "Mon" },
  { id: 1, label: "Tue" },
  { id: 2, label: "Wed" },
  { id: 3, label: "Thu" },
  { id: 4, label: "Fri" },
  { id: 5, label: "Sat" },
  { id: 6, label: "Sun" },
];

export default function Settings() {
  const { can } = useAuth();
  const { toast, ask } = useUi();
  const [cfg, setCfg] = useState(null);
  const [sync, setSync] = useState(null);
  const [backups, setBackups] = useState([]);
  const [schedule, setSchedule] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  function load() {
    api.get("/api/settings").then((d) => {
      setCfg(d.settings);
      setSync(d.sync);
      setSchedule(d.backup || null);
    });
    if (can("backup")) {
      api.get("/api/settings/backups").then((d) => {
        setBackups(d.items || []);
        setSchedule(d.schedule || null);
      });
    }
  }
  useEffect(load, []);

  async function save() {
    setError("");
    setSaving(true);
    try {
      const d = await api.put("/api/settings", { values: cfg });
      setCfg(d.settings);
      setSchedule(d.backup || schedule);
      toast("Configuration saved", "success");
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function restore(b) {
    const ok = await ask({
      title: "Restore this backup?",
      body: `${b.name}\nThe current workbook will be copied aside first.`,
      confirmLabel: "Restore",
      danger: true,
    });
    if (!ok) return;
    await api.post("/api/settings/backups/restore", { path: b.path });
    load();
    toast("Backup restored", "success");
    window.dispatchEvent(new CustomEvent("woms:data"));
  }

  if (!cfg) return <div className="text-sm text-slate-500">Loading settings…</div>;

  const mapping = cfg.mapping || {};

  return (
    <div className="space-y-5 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-slate-500">Excel location, column mapping, backups and business rules.</p>
      </div>
      {error && <div className="text-sm text-rose-600">{error}</div>}

      <div className="card p-5 space-y-3">
        <div className="font-semibold">Excel workbook</div>
        <div className="grid md:grid-cols-2 gap-3">
          <div>
            <label className="lbl">File path</label>
            <input value={cfg.excel_path} onChange={(e) => setCfg({ ...cfg, excel_path: e.target.value })} disabled={!can("settings")} />
          </div>
          <div>
            <label className="lbl">Worksheet</label>
            <input value={cfg.worksheet_name} onChange={(e) => setCfg({ ...cfg, worksheet_name: e.target.value })} disabled={!can("settings")} />
          </div>
          <div>
            <label className="lbl">Auto refresh (seconds)</label>
            <input
              type="number"
              value={cfg.auto_refresh_seconds}
              onChange={(e) => setCfg({ ...cfg, auto_refresh_seconds: Number(e.target.value) })}
              disabled={!can("settings")}
            />
          </div>
        </div>
        <div className="text-xs text-slate-500">
          Status: {sync?.synchronized ? "Synchronized" : "Not synchronized"} · {sync?.record_count} records · last write {sync?.last_write || "—"}
        </div>
      </div>

      {can("backup") && (
        <BackupPanel
          cfg={cfg}
          setCfg={setCfg}
          backups={backups}
          schedule={schedule}
          canSettings={can("settings")}
          onRestore={restore}
          onReload={load}
          toast={toast}
        />
      )}

      <div className="card p-5">
        <div className="font-semibold mb-3">Column mapping (Excel → application)</div>
        <div className="grid md:grid-cols-2 gap-3">
          {Object.entries(mapping).map(([k, v]) => (
            <div key={k}>
              <label className="lbl">{k}</label>
              <input
                value={v}
                disabled={!can("settings")}
                onChange={(e) => setCfg({ ...cfg, mapping: { ...mapping, [k]: e.target.value } })}
              />
            </div>
          ))}
        </div>
      </div>

      <div className="card p-5 grid md:grid-cols-2 gap-3">
        <ListField label="Open KPI statuses" value={cfg.status_open_values} onChange={(v) => setCfg({ ...cfg, status_open_values: v })} disabled={!can("settings")} />
        <ListField label="Placed statuses" value={cfg.placed_statuses} onChange={(v) => setCfg({ ...cfg, placed_statuses: v })} disabled={!can("settings")} />
        <ListField label="Closed statuses" value={cfg.closed_statuses} onChange={(v) => setCfg({ ...cfg, closed_statuses: v })} disabled={!can("settings")} />
        <ListField label="Pending statuses" value={cfg.pending_statuses} onChange={(v) => setCfg({ ...cfg, pending_statuses: v })} disabled={!can("settings")} />
        <ListField label="In-progress statuses" value={cfg.in_progress_statuses} onChange={(v) => setCfg({ ...cfg, in_progress_statuses: v })} disabled={!can("settings")} />
        <ListField label="Cancelled statuses" value={cfg.cancelled_statuses} onChange={(v) => setCfg({ ...cfg, cancelled_statuses: v })} disabled={!can("settings")} />
        <div className="md:col-span-2">
          <label className="lbl">Due-date offsets (purchase type: days)</label>
          <textarea
            rows={6}
            disabled={!can("settings")}
            value={Object.entries(cfg.due_offsets || {})
              .map(([k, v]) => `${k}: ${v}`)
              .join("\n")}
            onChange={(e) => {
              const next = {};
              e.target.value.split("\n").forEach((line) => {
                const [k, v] = line.split(":");
                if (!k || v == null) return;
                const days = Number(String(v).trim());
                if (Number.isFinite(days)) next[k.trim().toLowerCase()] = days;
              });
              setCfg({ ...cfg, due_offsets: next });
            }}
          />
          <p className="text-[11px] text-slate-500 mt-1">Default extra days when a type is missing: {cfg.due_offset_default_days ?? 14}. Excel due-date formulas are not overwritten.</p>
        </div>
        <div>
          <label className="lbl">Required fields by status</label>
          <textarea
            rows={4}
            disabled={!can("settings")}
            value={Object.entries(cfg.status_required_fields || {})
              .map(([k, v]) => `${k}: ${(v || []).join(", ")}`)
              .join("\n")}
            onChange={(e) => {
              const next = {};
              e.target.value.split("\n").forEach((line) => {
                const [k, v] = line.split(":");
                if (!k || v == null) return;
                const fields = v.split(",").map((s) => s.trim()).filter(Boolean);
                if (fields.length) next[k.trim()] = fields;
              });
              setCfg({ ...cfg, status_required_fields: next });
            }}
          />
          <p className="text-[11px] text-slate-500 mt-1">Example: PLACED: po_number. Uses internal field names from the mapping above.</p>
        </div>
        <div>
          <label className="lbl">Who can edit which fields</label>
          <textarea
            rows={4}
            disabled={!can("settings")}
            value={Object.entries(cfg.field_edit_roles || {})
              .map(([k, v]) => `${k}: ${(v || []).join(", ")}`)
              .join("\n")}
            onChange={(e) => {
              const next = {};
              e.target.value.split("\n").forEach((line) => {
                const [k, v] = line.split(":");
                if (!k || v == null) return;
                next[k.trim()] = v.split(",").map((s) => s.trim()).filter(Boolean);
              });
              setCfg({ ...cfg, field_edit_roles: next });
            }}
          />
          <p className="text-[11px] text-slate-500 mt-1">Example: supplier: admin, manager. Fields not listed can be edited by anyone with edit permission. Admin always can.</p>
        </div>
      </div>

      {can("settings") && (
        <button className="btn-primary" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save configuration"}
        </button>
      )}
    </div>
  );
}

function BackupPanel({ cfg, setCfg, backups, schedule, canSettings, onRestore, onReload, toast }) {
  const [browse, setBrowse] = useState(false);
  const [listing, setListing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [newFolder, setNewFolder] = useState("");
  const [rowRestore, setRowRestore] = useState(null);
  const days = cfg.backup_days?.length ? cfg.backup_days : [0, 1, 2, 3, 4, 5, 6];

  async function openBrowse(path) {
    const d = await api.get(`/api/settings/folders${path ? `?path=${encodeURIComponent(path)}` : ""}`);
    setListing(d);
    setBrowse(true);
  }

  async function createFolder() {
    const name = newFolder.trim();
    if (!name || !listing?.path) return;
    const sep = listing.path.includes("\\") && !listing.path.startsWith("/") ? "\\" : "/";
    const path = `${listing.path.replace(/[\\/]+$/, "")}${sep}${name}`;
    const d = await api.post("/api/settings/folders", { path });
    setNewFolder("");
    setListing(d.listing);
    toast("Folder created", "success");
  }

  function toggleDay(id) {
    const has = days.includes(id);
    const next = has ? days.filter((d) => d !== id) : [...days, id].sort((a, b) => a - b);
    setCfg({ ...cfg, backup_days: next.length ? next : [id] });
  }

  async function backupNow() {
    setBusy(true);
    try {
      await api.post("/api/settings/backups");
      onReload();
      toast("Backup created", "success");
    } catch (e) {
      toast(e.message || "Backup failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function runAuto() {
    setBusy(true);
    try {
      await api.post("/api/settings/backups/run-auto");
      onReload();
      toast("Automatic backup ran", "success");
    } catch (e) {
      toast(e.message || "Autobackup failed", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold flex items-center gap-2">
            <HardDrive size={16} /> Backup system
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Copies of <span className="font-mono">file.xlsx</span> go to the folder you choose. Autobackup runs while the app is open.
          </p>
        </div>
        <label className="inline-flex items-center gap-2 text-sm font-medium">
          <input
            type="checkbox"
            className="!w-auto"
            checked={!!cfg.backup_auto_enabled}
            disabled={!canSettings}
            onChange={(e) => setCfg({ ...cfg, backup_auto_enabled: e.target.checked })}
          />
          Autobackup
        </label>
      </div>

      <div className="p-5 space-y-4">
        <div>
          <label className="lbl">Backup folder</label>
          <div className="flex gap-2">
            <input
              value={cfg.backup_dir || ""}
              disabled={!canSettings}
              onChange={(e) => setCfg({ ...cfg, backup_dir: e.target.value })}
              placeholder="D:\\Backups\\Linkco or /data/backups"
            />
            <button className="btn-outline shrink-0" type="button" onClick={() => openBrowse(cfg.backup_dir)} disabled={!canSettings}>
              <FolderOpen size={14} /> Browse
            </button>
          </div>
        </div>

        <div className="grid md:grid-cols-3 gap-3">
          <div>
            <label className="lbl">Time</label>
            <input
              type="time"
              disabled={!canSettings}
              value={(cfg.backup_time || "02:00").slice(0, 5)}
              onChange={(e) => setCfg({ ...cfg, backup_time: e.target.value || "02:00" })}
            />
          </div>
          <div>
            <label className="lbl">Start date</label>
            <input
              type="date"
              disabled={!canSettings}
              value={cfg.backup_start_date || ""}
              onChange={(e) => setCfg({ ...cfg, backup_start_date: e.target.value })}
            />
          </div>
          <div>
            <label className="lbl">Ratio (keep last N)</label>
            <input
              type="number"
              min={0}
              disabled={!canSettings}
              value={cfg.backup_ratio ?? 14}
              onChange={(e) => setCfg({ ...cfg, backup_ratio: Number(e.target.value) })}
            />
            <p className="text-[11px] text-slate-500 mt-1">0 keeps every auto/manual copy. Write-safety copies are not pruned.</p>
          </div>
        </div>

        <div>
          <label className="lbl">Days</label>
          <div className="flex flex-wrap gap-1.5">
            {DAYS.map((d) => {
              const on = days.includes(d.id);
              return (
                <button
                  key={d.id}
                  type="button"
                  disabled={!canSettings}
                  onClick={() => toggleDay(d.id)}
                  className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold border ${
                    on
                      ? "bg-brand-700 text-white border-brand-700"
                      : "border-slate-200 dark:border-white/10 text-slate-600 dark:text-slate-300"
                  }`}
                >
                  {d.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <CalendarClock size={14} />
          <span>{cfg.backup_auto_enabled ? `Next run ${schedule?.next_run || "—"}` : "Autobackup is off"}</span>
          <span>· last auto {schedule?.last_auto_backup || "never"}</span>
          <span className="ml-auto flex gap-2">
            <button className="btn-outline !py-1 !px-2 text-xs" onClick={backupNow} disabled={busy}>
              {busy ? "Working…" : "Backup now"}
            </button>
            <button className="btn-outline !py-1 !px-2 text-xs" onClick={runAuto} disabled={busy || !cfg.backup_auto_enabled}>
              Run autobackup
            </button>
          </span>
        </div>
      </div>

      <table className="data">
        <thead>
          <tr>
            <th>File</th>
            <th>Kind</th>
            <th>Modified</th>
            <th>Size</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {backups.map((b) => (
            <tr key={b.path} className="!cursor-default">
              <td className="font-mono text-xs">{b.name}</td>
              <td className="uppercase text-[11px] text-slate-500">{b.reason || "—"}</td>
              <td>{b.modified}</td>
              <td>{Math.round(b.size / 1024)} KB</td>
              <td>
                <div className="flex gap-1 justify-end">
                  <button className="btn-outline !py-1 !px-2 text-xs" onClick={() => onRestore(b)}>
                    Restore file
                  </button>
                  <button
                    className="btn-outline !py-1 !px-2 text-xs"
                    onClick={() => setRowRestore({ path: b.path, name: b.name, record_id: "", work_order_id: "", site: "", preview: null, busy: false })}
                  >
                    Restore row
                  </button>
                </div>
              </td>
            </tr>
          ))}
          {!backups.length && (
            <tr className="!cursor-default">
              <td colSpan={5} className="text-center text-slate-400 py-8">
                No backups yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {browse && listing && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={() => setBrowse(false)}>
          <div className="card w-full max-w-lg p-4 space-y-3" onClick={(e) => e.stopPropagation()}>
            <div className="font-semibold">Select backup folder</div>
            <div className="font-mono text-xs break-all text-slate-500">{listing.path}</div>
            {listing.error && <div className="text-sm text-rose-600">{listing.error}</div>}
            <div className="flex gap-2">
              <button className="btn-outline text-xs" type="button" onClick={() => listing.parent && openBrowse(listing.parent)} disabled={!listing.parent}>
                Up
              </button>
              {(listing.roots || []).slice(0, 6).map((r) => (
                <button key={r.path} className="btn-ghost text-xs !px-2" type="button" onClick={() => openBrowse(r.path)}>
                  {r.name || r.path}
                </button>
              ))}
            </div>
            <div className="max-h-64 overflow-auto rounded-lg border border-slate-200 dark:border-white/10">
              {(listing.folders || []).map((f) => (
                <button
                  key={f.path}
                  type="button"
                  className="w-full text-left px-3 py-2 text-sm hover:bg-slate-50 dark:hover:bg-white/5 border-b border-slate-100 dark:border-white/5 last:border-0"
                  onClick={() => openBrowse(f.path)}
                >
                  {f.name}
                </button>
              ))}
              {!(listing.folders || []).length && <div className="px-3 py-6 text-center text-sm text-slate-400">No subfolders</div>}
            </div>
            <div className="flex gap-2">
              <input placeholder="New folder name" value={newFolder} onChange={(e) => setNewFolder(e.target.value)} />
              <button className="btn-outline shrink-0" type="button" onClick={createFolder} disabled={!newFolder.trim()}>
                Create
              </button>
            </div>
            <div className="flex justify-end gap-2">
              <button className="btn-ghost" type="button" onClick={() => setBrowse(false)}>
                Cancel
              </button>
              <button
                className="btn-primary"
                type="button"
                disabled={!listing.exists}
                onClick={() => {
                  setCfg({ ...cfg, backup_dir: listing.path });
                  setBrowse(false);
                }}
              >
                Use this folder
              </button>
            </div>
          </div>
        </div>
      )}

      {rowRestore && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={() => setRowRestore(null)}>
          <div className="card w-full max-w-lg p-4 space-y-3" onClick={(e) => e.stopPropagation()}>
            <div className="font-semibold">Restore one row from {rowRestore.name}</div>
            <p className="text-xs text-slate-500">
              Matches live Excel by record id, then WO # + site. Only mapped data fields are written; formula columns are skipped. The current workbook is backed up first.
            </p>
            <div>
              <label className="lbl">Record id</label>
              <input
                value={rowRestore.record_id}
                onChange={(e) => setRowRestore({ ...rowRestore, record_id: e.target.value })}
                placeholder="SH5-SH1:12"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="lbl">IM WO #</label>
                <input
                  value={rowRestore.work_order_id}
                  onChange={(e) => setRowRestore({ ...rowRestore, work_order_id: e.target.value })}
                />
              </div>
              <div>
                <label className="lbl">Site</label>
                <input
                  value={rowRestore.site}
                  onChange={(e) => setRowRestore({ ...rowRestore, site: e.target.value })}
                  placeholder="F5"
                />
              </div>
            </div>
            {rowRestore.preview && (
              <div className="max-h-48 overflow-auto rounded-lg border border-slate-200 dark:border-white/10 text-sm">
                {!(rowRestore.preview.diffs || []).length ? (
                  <div className="px-3 py-4 text-slate-500">No mapped field differences.</div>
                ) : (
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Field</th>
                        <th>Live</th>
                        <th>Backup</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rowRestore.preview.diffs.map((d) => (
                        <tr key={d.field} className="!cursor-default">
                          <td>{d.field}</td>
                          <td className="max-w-[140px] truncate text-slate-500">{d.current || "—"}</td>
                          <td className="max-w-[140px] truncate">{d.backup || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {!rowRestore.preview.matched_live && (
                  <div className="px-3 py-2 text-xs text-rose-600">That row is not in the live workbook.</div>
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
                    onReload();
                    window.dispatchEvent(new CustomEvent("woms:data"));
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

function ListField({ label, value, onChange, disabled }) {
  return (
    <div>
      <label className="lbl">{label}</label>
      <input
        disabled={disabled}
        value={(value || []).join(", ")}
        onChange={(e) => onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
      />
    </div>
  );
}
