import { useEffect, useRef, useState } from "react";
import { CalendarClock, Download, FolderOpen, HardDrive, Upload } from "lucide-react";
import { api, waitForJob } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";
import JobProgress from "../components/JobProgress.jsx";

function setJobBusy(on) {
  if (on) sessionStorage.setItem("woms_job_busy", "1");
  else sessionStorage.removeItem("woms_job_busy");
}

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
  const [headers, setHeaders] = useState([]);
  const [suggest, setSuggest] = useState({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  function load() {
    api.get("/api/settings").then((d) => {
      setCfg(d.settings);
      setSync(d.sync);
      setSchedule(d.backup || null);
    });
    api
      .get("/api/settings/mapping-scan")
      .then((d) => {
        setHeaders(d.headers || []);
        setSuggest(d.suggestions || {});
      })
      .catch(() => {});
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
    const full = !!b.has_db;
    const ok = await ask({
      title: full ? "Restore this snapshot?" : "Restore Excel replica only?",
      body: full
        ? `${b.name}\nThis rolls back live work-order history (database) and the Excel replica. A pre-restore snapshot is taken first.`
        : `${b.name}\nThis replaces file.xlsx only. Live records in the database are not changed. Seed from Excel afterwards if you want those rows.`,
      confirmLabel: full ? "Restore snapshot" : "Restore Excel",
      danger: true,
    });
    if (!ok) return;
    const d = await api.post("/api/settings/backups/restore", { path: b.path });
    load();
    toast(
      d.database ? "Snapshot restored (database + Excel)" : "Excel replica restored. Database was not changed.",
      "success"
    );
    window.dispatchEvent(new CustomEvent("woms:data"));
  }

  if (!cfg) return <div className="text-sm text-slate-500">Loading settings…</div>;

  const mapping = cfg.mapping || {};

  return (
    <div className="space-y-5 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-slate-500">Database history, Excel backup, column mapping and business rules.</p>
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
          Database is the live history · Excel is a midnight replica · {sync?.record_count} records · last write {sync?.last_write || "—"}
        </div>
      </div>

      {can("settings") && <DatabasePanel toast={toast} ask={ask} onReload={load} />}

      {can("settings") && <EmailPanel cfg={cfg} setCfg={setCfg} toast={toast} />}

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
          ask={ask}
        />
      )}

      <div className="card p-5">
        <div className="font-semibold mb-1">Column mapping wizard</div>
        <p className="text-xs text-slate-500 mb-3">
          Headers scanned from the live workbook. Pick the Excel column for each app field. Suggested matches are from the current file, not invented names.
        </p>
        <div className="grid md:grid-cols-2 gap-3">
          {Object.entries(mapping).map(([k, v]) => {
            const hint = suggest[k] || {};
            const missing = headers.length && v && !headers.some((h) => String(h).toLowerCase() === String(v).toLowerCase());
            return (
              <div key={k}>
                <label className="lbl">
                  {k}
                  {missing ? <span className="text-rose-600 font-normal"> · not in live headers</span> : ""}
                </label>
                <select
                  value={v || ""}
                  disabled={!can("settings")}
                  onChange={(e) => setCfg({ ...cfg, mapping: { ...mapping, [k]: e.target.value } })}
                >
                  <option value="">—</option>
                  {v && !headers.includes(v) && <option value={v}>{v} (saved)</option>}
                  {headers.map((h) => (
                    <option key={h} value={h}>
                      {h}
                    </option>
                  ))}
                </select>
                {hint.suggested && hint.suggested !== v && (
                  <button
                    type="button"
                    className="text-[11px] text-brand-700 dark:text-cyan-300 mt-1 hover:underline"
                    onClick={() => setCfg({ ...cfg, mapping: { ...mapping, [k]: hint.suggested } })}
                  >
                    Use suggested: {hint.suggested}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="card p-5 grid md:grid-cols-2 gap-3">
        <ListField label="Open KPI statuses" value={cfg.status_open_values} onChange={(v) => setCfg({ ...cfg, status_open_values: v })} disabled={!can("settings")} />
        <ListField label="Placed statuses" value={cfg.placed_statuses} onChange={(v) => setCfg({ ...cfg, placed_statuses: v })} disabled={!can("settings")} />
        <ListField label="Closed statuses" value={cfg.closed_statuses} onChange={(v) => setCfg({ ...cfg, closed_statuses: v })} disabled={!can("settings")} />
        <ListField label="Pending statuses" value={cfg.pending_statuses} onChange={(v) => setCfg({ ...cfg, pending_statuses: v })} disabled={!can("settings")} />
        <ListField label="Delay: Open (only if due date passed)" value={cfg.delay_open_statuses} onChange={(v) => setCfg({ ...cfg, delay_open_statuses: v })} disabled={!can("settings")} />
        <ListField label="Delay: Pending" value={cfg.delay_pending_statuses} onChange={(v) => setCfg({ ...cfg, delay_pending_statuses: v })} disabled={!can("settings")} />
        <ListField label="Never count as delay" value={cfg.delay_excluded_statuses} onChange={(v) => setCfg({ ...cfg, delay_excluded_statuses: v })} disabled={!can("settings")} />
        <ListField label="Extra sites" value={cfg.extra_sites} onChange={(v) => setCfg({ ...cfg, extra_sites: v })} disabled={!can("settings")} />
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
        <ListField
          label="Delivery statuses"
          value={cfg.delivery_statuses}
          onChange={(v) => setCfg({ ...cfg, delivery_statuses: v })}
          disabled={!can("settings")}
        />
        <p className="text-[11px] text-slate-500 md:col-span-2 -mt-2">
          Merged with unique Excel Delivery Status values. Do not replace live workbook values — extras only appear in the dropdown.
        </p>
        <ListField
          label="Status changes that need a remark"
          value={cfg.status_change_remarks}
          onChange={(v) => setCfg({ ...cfg, status_change_remarks: v })}
          disabled={!can("settings")}
        />
        <p className="text-[11px] text-slate-500 md:col-span-2 -mt-2">Example: *-&gt;ON HOLD, *-&gt;CLOSED. Same pattern as required fields. Blank remark is rejected on save and bulk status change.</p>
      </div>

      {can("settings") && (
        <button className="btn-primary" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save configuration"}
        </button>
      )}
    </div>
  );
}

function DatabasePanel({ toast, ask, onReload }) {
  const { logout } = useAuth();
  const [info, setInfo] = useState(null);
  const [busy, setBusy] = useState("");
  const [confirm, setConfirm] = useState("");
  const [jobUi, setJobUi] = useState(null);
  const uploadRef = useRef(null);

  function loadInfo() {
    api
      .get("/api/settings/database")
      .then(setInfo)
      .catch((e) => toast(e.message || "Could not read database status", "error"));
  }
  useEffect(loadInfo, []);

  async function seed() {
    const ok = await ask({
      title: "Seed the database from Excel?",
      body: "This replaces work-order history in SQLite with the current file.xlsx. Users, chat and settings stay. Mapping in app_config.json is not changed.",
      confirmLabel: "Seed from Excel",
    });
    if (!ok) return;
    setBusy("seed");
    try {
      const d = await api.post("/api/settings/database/seed", {});
      toast(`Seeded ${d.count ?? 0} material requests from Excel`, "success");
      loadInfo();
      onReload();
      window.dispatchEvent(new CustomEvent("woms:data"));
    } catch (e) {
      const retry = await ask({
        title: "Seed failed",
        body: e.message || "Could not seed the database from Excel.",
        confirmLabel: "Retry",
        danger: true,
      });
      if (retry) return seed();
    } finally {
      setBusy("");
    }
  }

  async function resetDb() {
    if (confirm.trim() !== "DELETE") {
      toast("Type DELETE to confirm wiping the database", "error");
      return;
    }
    const ok = await ask({
      title: "Wipe the entire database?",
      body: "Users, chat, settings, attachments and work orders are deleted. Default logins are recreated (admin/admin123) and must change password on first sign-in. Then current Excel is seeded. Column mapping in app_config.json is kept. You will need to sign in again.",
      confirmLabel: "Wipe database",
      danger: true,
    });
    if (!ok) return;
    setBusy("reset");
    try {
      const d = await api.post("/api/settings/database/reset", { confirm: "DELETE" });
      const seedErr = d.seed && !d.seed.ok ? `\nExcel seed: ${d.seed.error || "failed"}` : "";
      toast(`Database reset. Default users restored.${seedErr}`, seedErr ? "error" : "success");
      setConfirm("");
      await logout();
      window.location.href = "/login";
    } catch (e) {
      const retry = await ask({
        title: "Reset failed",
        body: e.message || "Could not wipe the database.",
        confirmLabel: "Retry",
        danger: true,
      });
      if (retry) return resetDb();
    } finally {
      setBusy("");
    }
  }

  async function upload(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const ok = await ask({
      title: "Replace live Excel and seed the database?",
      body: `${file.name}\nThis copies the file over file.xlsx, then loads those rows into SQLite. Users are not deleted. Use Reset database if you also want to wipe logins and chat.`,
      confirmLabel: "Upload and seed",
    });
    if (!ok) return;
    setBusy("upload");
    setJobBusy(true);
    setJobUi({
      title: "Upload Excel then seed",
      upload: 1,
      apply: 0,
      applyLabel: "Applying backup",
      message: "Uploading Excel…",
    });
    try {
      const fd = new FormData();
      fd.append("file", file);
      const started = await api.uploadWithProgress("/api/settings/jobs/excel-upload", fd, (pct) => {
        setJobUi((prev) => prev && { ...prev, upload: pct, message: "Uploading Excel…" });
      });
      setJobUi((prev) => prev && { ...prev, upload: 100, apply: 8, message: "Applying backup…" });
      const st = await waitForJob(started.job_id, (tick) => {
        setJobUi((prev) =>
          prev && {
            ...prev,
            upload: 100,
            apply: Math.max(8, tick.progress || 0),
            message: tick.message || "Applying backup…",
          }
        );
      });
      const count = st.result?.seed?.count ?? st.result?.sync?.record_count ?? 0;
      setJobUi((prev) =>
        prev && {
          ...prev,
          upload: 100,
          apply: 100,
          done: true,
          doneLabel: `Applied backup · ${count} material requests seeded`,
          message: "",
        }
      );
      toast(`Uploaded and seeded ${count} rows`, "success");
      loadInfo();
      onReload();
      window.dispatchEvent(new CustomEvent("woms:data"));
    } catch (err) {
      setJobUi((prev) => prev && { ...prev, error: err.message || "Could not upload Excel." });
      const retry = await ask({
        title: "Upload failed",
        body: err.message || "Could not upload Excel.",
        confirmLabel: "Retry",
        danger: true,
      });
      if (retry) uploadRef.current?.click();
    } finally {
      setBusy("");
      setJobBusy(false);
    }
  }

  return (
    <div className="card p-5 space-y-3">
      <div className="font-semibold">Work-order database</div>
      <p className="text-xs text-slate-500">
        SQLite is the live material-request history. Create, update and delete write the database only. At midnight (and Backup now) every row is exported into file.xlsx and SQLite is snapshotted. Copies older than a month move to backups/archive; archives older than six months are deleted. A hard refresh does not pull Excel over the database.
      </p>
      <div className="text-xs text-slate-500">
        {info ? (
          <>
            {info.record_count ?? 0} records · {info.user_count ?? 0} users · last seed {info.last_seed || "—"} · Excel {info.excel_available ? "available" : "missing"}
          </>
        ) : (
          "Loading…"
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <button className="btn-outline" type="button" onClick={seed} disabled={!!busy}>
          {busy === "seed" ? "Seeding…" : "Seed from Excel"}
        </button>
        <input ref={uploadRef} type="file" accept=".xlsx,.xlsm" className="hidden" onChange={upload} />
        <button className="btn-outline" type="button" onClick={() => uploadRef.current?.click()} disabled={!!busy}>
          {busy === "upload" ? "Uploading…" : "Upload Excel then seed"}
        </button>
      </div>
      <div className="rounded-xl border border-rose-200 dark:border-rose-500/30 p-3 space-y-2">
        <div className="text-sm font-medium text-rose-700 dark:text-rose-200">Reset database</div>
        <p className="text-xs text-slate-500">
          Deletes users, chat, settings, attachments and work orders, creates a fresh database with default logins, then seeds the current Excel file. Type DELETE to enable.
        </p>
        <div className="flex flex-wrap gap-2">
          <input
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Type DELETE"
            className="max-w-[160px]"
            disabled={!!busy}
          />
          <button className="btn-danger" type="button" onClick={resetDb} disabled={!!busy || confirm.trim() !== "DELETE"}>
            {busy === "reset" ? "Resetting…" : "Reset database"}
          </button>
        </div>
      </div>
      {jobUi && (
        <JobProgress
          title={jobUi.title}
          uploadPct={jobUi.upload}
          applyPct={jobUi.apply}
          applyLabel={jobUi.applyLabel}
          message={jobUi.message}
          error={jobUi.error}
          done={jobUi.done}
          doneLabel={jobUi.doneLabel}
          onClose={() => setJobUi(null)}
        />
      )}
    </div>
  );
}

function EmailPanel({ cfg, setCfg, toast }) {
  const [testTo, setTestTo] = useState("");
  const [busy, setBusy] = useState(false);
  const provider = cfg.email_provider || "off";

  async function sendTest() {
    setBusy(true);
    try {
      const d = await api.post("/api/settings/email/test", { to: testTo });
      toast(`Test sent to ${d.to}`, "success");
    } catch (e) {
      toast(e.message || "Could not send test email", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card p-5 space-y-3">
      <div>
        <div className="font-semibold">Email</div>
        <p className="text-xs text-slate-500">
          SMTP or Resend sends verification links, password resets, and PO / assignment requests. The in-app inbox still
          works if mail is off. Secrets are never returned after save.
        </p>
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        <div>
          <label className="lbl">Provider</label>
          <select value={provider} onChange={(e) => setCfg({ ...cfg, email_provider: e.target.value })}>
            <option value="off">Off</option>
            <option value="smtp">SMTP</option>
            <option value="resend">Resend API</option>
          </select>
        </div>
        <div>
          <label className="lbl">Public URL (for links in emails)</label>
          <input
            value={cfg.email_public_url || ""}
            onChange={(e) => setCfg({ ...cfg, email_public_url: e.target.value })}
            placeholder="https://mr.example.com"
          />
        </div>
        <div>
          <label className="lbl">From name</label>
          <input value={cfg.email_from_name || ""} onChange={(e) => setCfg({ ...cfg, email_from_name: e.target.value })} />
        </div>
        <div>
          <label className="lbl">From email</label>
          <input
            type="email"
            value={cfg.email_from_address || ""}
            onChange={(e) => setCfg({ ...cfg, email_from_address: e.target.value })}
            placeholder="noreply@linkco.com.qa"
          />
        </div>
      </div>
      <div className="flex flex-wrap gap-4 text-sm">
        <label className="inline-flex items-center gap-2">
          <input
            type="checkbox"
            className="!w-auto"
            checked={cfg.email_notify_po !== false}
            onChange={(e) => setCfg({ ...cfg, email_notify_po: e.target.checked })}
          />
          PO signature requests
        </label>
        <label className="inline-flex items-center gap-2">
          <input
            type="checkbox"
            className="!w-auto"
            checked={cfg.email_notify_assign !== false}
            onChange={(e) => setCfg({ ...cfg, email_notify_assign: e.target.checked })}
          />
          Assign-to
        </label>
        <label className="inline-flex items-center gap-2">
          <input
            type="checkbox"
            className="!w-auto"
            checked={cfg.email_notify_mention !== false}
            onChange={(e) => setCfg({ ...cfg, email_notify_mention: e.target.checked })}
          />
          @mentions
        </label>
        <label className="inline-flex items-center gap-2">
          <input
            type="checkbox"
            className="!w-auto"
            checked={!!cfg.email_notify_chat}
            onChange={(e) => setCfg({ ...cfg, email_notify_chat: e.target.checked })}
          />
          Chat / follow
        </label>
      </div>
      {provider === "smtp" && (
        <div className="grid md:grid-cols-2 gap-3">
          <div>
            <label className="lbl">SMTP host</label>
            <input value={cfg.smtp_host || ""} onChange={(e) => setCfg({ ...cfg, smtp_host: e.target.value })} placeholder="smtp.office365.com" />
          </div>
          <div>
            <label className="lbl">Port</label>
            <input
              type="number"
              value={cfg.smtp_port ?? 587}
              onChange={(e) => setCfg({ ...cfg, smtp_port: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className="lbl">Security</label>
            <select value={cfg.smtp_security || "starttls"} onChange={(e) => setCfg({ ...cfg, smtp_security: e.target.value })}>
              <option value="starttls">STARTTLS (587)</option>
              <option value="ssl">SSL (465)</option>
              <option value="none">None</option>
            </select>
          </div>
          <div>
            <label className="lbl">Username</label>
            <input value={cfg.smtp_username || ""} onChange={(e) => setCfg({ ...cfg, smtp_username: e.target.value })} />
          </div>
          <div className="md:col-span-2">
            <label className="lbl">Password {cfg.smtp_password_set ? "· saved" : ""}</label>
            <input
              type="password"
              value={cfg.smtp_password || ""}
              onChange={(e) => setCfg({ ...cfg, smtp_password: e.target.value })}
              placeholder={cfg.smtp_password_set ? "Leave blank to keep the saved password" : ""}
              autoComplete="new-password"
            />
          </div>
        </div>
      )}
      {provider === "resend" && (
        <div>
          <label className="lbl">Resend API key {cfg.resend_api_key_set ? "· saved" : ""}</label>
          <input
            type="password"
            value={cfg.resend_api_key || ""}
            onChange={(e) => setCfg({ ...cfg, resend_api_key: e.target.value })}
            placeholder={cfg.resend_api_key_set ? "Leave blank to keep the saved key" : "re_…"}
            autoComplete="new-password"
          />
        </div>
      )}
      {provider !== "off" && (
        <div className="flex flex-wrap gap-2 items-end">
          <div className="flex-1 min-w-[12rem]">
            <label className="lbl">Send a test to</label>
            <input type="email" value={testTo} onChange={(e) => setTestTo(e.target.value)} placeholder="you@company.com" />
          </div>
          <button type="button" className="btn-outline" disabled={busy} onClick={sendTest}>
            {busy ? "Sending…" : "Send test"}
          </button>
        </div>
      )}
      <p className="text-[11px] text-slate-500">Save configuration after changing provider or keys. Then send a test.</p>
    </div>
  );
}

function BackupPanel({ cfg, setCfg, backups, schedule, canSettings, onRestore, onReload, toast, ask }) {
  const [browse, setBrowse] = useState(false);
  const [listing, setListing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [newFolder, setNewFolder] = useState("");
  const [rowRestore, setRowRestore] = useState(null);
  const [healthMap, setHealthMap] = useState({});
  const [jobUi, setJobUi] = useState(null);
  const uploadRef = useRef(null);
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
      toast("Snapshot created (database + Excel)", "success");
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

  async function uploadBackup(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const d = await api.upload("/api/settings/backups/upload", fd);
      if (d.health) setHealthMap((prev) => ({ ...prev, [d.path]: d.health }));
      onReload();
      toast(
        d.health && !d.health.ok
          ? `Saved as backup, but health check failed (${d.health.error || "row count mismatch"})`
          : `Backup uploaded · ${d.name}`,
        d.health && !d.health.ok ? "error" : "success"
      );
      if (d.path) {
        await onRestore({ path: d.path, name: d.name, has_db: !!d.has_db });
      }
    } catch (err) {
      toast(err.message || "Upload failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function downloadBackup(b) {
    const stem = String(b.name || "backup").replace(/\.(xlsx|xlsm|db)$/i, "");
    const filename = b.has_db ? `${stem}.zip` : b.name;
    try {
      await api.download(`/api/settings/backups/download?path=${encodeURIComponent(b.path)}`, filename);
      toast(b.has_db ? "Downloaded snapshot zip (Excel + database)" : "Downloaded Excel backup", "success");
    } catch (err) {
      toast(err.message || "Download failed", "error");
    }
  }

  return (
    <div className="card overflow-hidden" data-tour="backup">
      <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold flex items-center gap-2">
            <HardDrive size={16} /> Backup system
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Midnight and Backup now dump the database into Excel, then snapshot both. Download a zip of the pair, or upload an .xlsx, .db, or zip, then Restore.
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
      {!cfg.backup_auto_enabled && (
        <div className="mx-5 mt-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-100">
          Nightly autobackup is off. Turn it on and Save configuration so the database is dumped to Excel and both are snapshotted at the scheduled time.
        </div>
      )}

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
              value={(cfg.backup_time || "00:00").slice(0, 5)}
              onChange={(e) => setCfg({ ...cfg, backup_time: e.target.value || "00:00" })}
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
            <p className="text-[11px] text-slate-500 mt-1">Optional extra cap on recent auto/manual copies. Age archive is the main retention.</p>
          </div>
          <div>
            <label className="lbl">Archive after (days)</label>
            <input
              type="number"
              min={1}
              disabled={!canSettings}
              value={cfg.backup_archive_days ?? 30}
              onChange={(e) => setCfg({ ...cfg, backup_archive_days: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className="lbl">Delete archives after (days)</label>
            <input
              type="number"
              min={1}
              disabled={!canSettings}
              value={cfg.backup_archive_keep_days ?? 180}
              onChange={(e) => setCfg({ ...cfg, backup_archive_keep_days: Number(e.target.value) })}
            />
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
          {schedule?.last_auto_backup_health && (
            <span className={schedule.last_auto_backup_health.ok ? "text-emerald-700" : "text-rose-600"}>
              · {schedule.last_auto_backup_health.ok
                ? `${schedule.last_auto_backup_health.backup_count} rows vs live ${schedule.last_auto_backup_health.live_count}`
                : `backup health fail: ${schedule.last_auto_backup_health.error || "row count mismatch"}`}
            </span>
          )}
          <span className="ml-auto flex gap-2">
            <input
              ref={uploadRef}
              type="file"
              accept=".xlsx,.xlsm,.db,.zip,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/zip"
              className="hidden"
              onChange={uploadBackup}
            />
            <button className="btn-outline !py-1 !px-2 text-xs" type="button" onClick={() => uploadRef.current?.click()} disabled={busy}>
              <Upload size={12} /> Upload & restore
            </button>
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
            <th>DB</th>
            <th>Modified</th>
            <th>Size</th>
            <th>Health</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {backups.map((b) => {
            const h = healthMap[b.path];
            return (
              <tr key={b.path} className="!cursor-default">
                <td className="font-mono text-xs">{b.name}</td>
                <td className="uppercase text-[11px] text-slate-500">{b.reason || "—"}</td>
                <td className="text-xs">{b.has_db ? "Yes" : "Excel only"}</td>
                <td>{b.modified}</td>
                <td>{Math.round(b.size / 1024)} KB</td>
                <td className={`text-xs ${h && !h.ok ? "text-rose-600" : ""}`}>
                  {h ? (h.ok ? `${h.backup_count} / live ${h.live_count}` : h.error || "mismatch") : "—"}
                </td>
                <td>
                  <div className="flex gap-1 justify-end flex-wrap">
                    <button
                      className="btn-outline !py-1 !px-2 text-xs"
                      onClick={() => downloadBackup(b)}
                    >
                      <Download size={12} /> Download
                    </button>
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
                    <button className="btn-outline !py-1 !px-2 text-xs" onClick={() => onRestore(b)}>
                      {b.has_db ? "Restore" : "Restore Excel"}
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
            );
          })}
          {!backups.length && (
            <tr className="!cursor-default">
              <td colSpan={7} className="text-center text-slate-400 py-8">
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
      {jobUi && (
        <JobProgress
          title={jobUi.title}
          uploadPct={jobUi.upload}
          applyPct={jobUi.apply}
          applyLabel={jobUi.applyLabel}
          message={jobUi.message}
          error={jobUi.error}
          done={jobUi.done}
          doneLabel={jobUi.doneLabel}
          onClose={() => setJobUi(null)}
        />
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
