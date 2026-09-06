import { useEffect, useState } from "react";
import { api } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";

export default function Settings() {
  const { can } = useAuth();
  const { toast, ask } = useUi();
  const [cfg, setCfg] = useState(null);
  const [sync, setSync] = useState(null);
  const [backups, setBackups] = useState([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  function load() {
    api.get("/api/settings").then((d) => {
      setCfg(d.settings);
      setSync(d.sync);
    });
    if (can("backup")) api.get("/api/settings/backups").then((d) => setBackups(d.items || []));
  }
  useEffect(load, []);

  async function save() {
    setError("");
    setSaving(true);
    try {
      const d = await api.put("/api/settings", { values: cfg });
      setCfg(d.settings);
      toast("Configuration saved", "success");
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
        <p className="text-sm text-slate-500">Excel location, column mapping and business rules.</p>
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
            <label className="lbl">Backup directory</label>
            <input value={cfg.backup_dir} onChange={(e) => setCfg({ ...cfg, backup_dir: e.target.value })} disabled={!can("settings")} />
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
        <ListField label="Closed statuses" value={cfg.closed_statuses} onChange={(v) => setCfg({ ...cfg, closed_statuses: v })} disabled={!can("settings")} />
        <ListField label="Pending statuses" value={cfg.pending_statuses} onChange={(v) => setCfg({ ...cfg, pending_statuses: v })} disabled={!can("settings")} />
        <ListField label="In-progress statuses" value={cfg.in_progress_statuses} onChange={(v) => setCfg({ ...cfg, in_progress_statuses: v })} disabled={!can("settings")} />
        <ListField label="Cancelled statuses" value={cfg.cancelled_statuses} onChange={(v) => setCfg({ ...cfg, cancelled_statuses: v })} disabled={!can("settings")} />
      </div>

      {can("settings") && (
        <button className="btn-primary" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save configuration"}
        </button>
      )}

      {can("backup") && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 flex items-center justify-between">
            <div className="font-semibold">Backups</div>
            <button
              className="btn-outline"
              onClick={async () => {
                await api.post("/api/settings/backups");
                load();
                toast("Backup created", "success");
              }}
            >
              Create backup now
            </button>
          </div>
          <table className="data">
            <thead>
              <tr>
                <th>File</th>
                <th>Modified</th>
                <th>Size</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {backups.map((b) => (
                <tr key={b.path} className="!cursor-default">
                  <td className="font-mono text-xs">{b.name}</td>
                  <td>{b.modified}</td>
                  <td>{Math.round(b.size / 1024)} KB</td>
                  <td>
                    <button className="btn-outline !py-1 !px-2 text-xs" onClick={() => restore(b)}>
                      Restore
                    </button>
                  </td>
                </tr>
              ))}
              {!backups.length && (
                <tr className="!cursor-default">
                  <td colSpan={4} className="text-center text-slate-400 py-8">
                    No backups yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
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
