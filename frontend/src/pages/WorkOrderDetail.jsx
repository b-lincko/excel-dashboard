import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

const FIELDS = [
  ["work_order_id", "IM Work Order #", "text", true],
  ["department", "Site", "site"],
  ["status", "STATUS", "status"],
  ["priority", "WO Priority Level", "priority"],
  ["assigned_to", "Assign to", "assigned_to"],
  ["work_type", "Purchase Type", "work_type"],
  ["location", "WO Asset Name", "text"],
  ["created_date", "MR Received Date", "datetime"],
  ["due_date", "Due date (computed from purchase type)", "datetime", true],
  ["completion_date", "IM WO Completion", "datetime"],
  ["scheduled_date", "Date of PO / Expected PO / RFQ Sent", "datetime"],
  ["closed_date", "ETA / Expected RFQ Response", "datetime"],
  ["supplier", "Supplier Name", "text"],
  ["po_number", "PO NO #", "text"],
  ["issue", "Delivery Status", "issue"],
  ["description", "Required Material Details", "textarea"],
  ["remarks", "REMARKS / NOTES", "textarea"],
];

function toInput(val) {
  if (!val) return "";
  return String(val).replace(" ", "T").slice(0, 16);
}
function fromInput(val) {
  if (!val) return "";
  return val.replace("T", " ");
}

export default function WorkOrderDetail() {
  const { id } = useParams();
  const isNew = !id;
  const nav = useNavigate();
  const { can } = useAuth();
  const [form, setForm] = useState({});
  const [original, setOriginal] = useState({});
  const [options, setOptions] = useState({});
  const [syncToken, setSyncToken] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [conflict, setConflict] = useState(null);
  const [busy, setBusy] = useState(false);
  const [meta, setMeta] = useState(null);

  useEffect(() => {
    api.get("/api/work-orders/options").then((d) => setOptions(d.options || {})).catch(() => {});
    if (!isNew) {
      api
        .get(`/api/work-orders/${encodeURIComponent(id)}`)
        .then((d) => {
          setForm(d.item);
          setOriginal(d.item);
          setSyncToken(d.sync_token);
          setMeta(d.item);
        })
        .catch((e) => setError(e.message));
    } else {
      setForm({
        status: "OPEN",
        priority: "MEDIUM",
        created_date: new Date().toISOString().slice(0, 16).replace("T", " "),
        department: "SH5-SH1",
      });
    }
  }, [id, isNew]);

  function setField(k, v) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function save(force = false) {
    setBusy(true);
    setError("");
    setSuccess("");
    setConflict(null);
    try {
      if (isNew) {
        const d = await api.post("/api/work-orders", { data: form });
        setSuccess("Material request created and written to Excel.");
        nav(`/work-orders/${encodeURIComponent(d.item.record_id || d.item.work_order_id)}`);
      } else {
        const skip = new Set([
          "is_closed",
          "is_open",
          "is_overdue",
          "is_pending",
          "is_in_progress",
          "aging_days",
          "closing_days",
          "days_overdue",
          "open_reason",
          "record_id",
          "due_date",
        ]);
        const changes = {};
        Object.keys(form).forEach((k) => {
          if (k.startsWith("_") || skip.has(k)) return;
          if (String(form[k] ?? "") !== String(original[k] ?? "")) changes[k] = form[k];
        });
        const d = await api.put(`/api/work-orders/${encodeURIComponent(id)}`, {
          changes,
          sync_token: syncToken,
          force,
        });
        setForm(d.item);
        setOriginal(d.item);
        setMeta(d.item);
        setSyncToken(d.sync_token);
        setSuccess("Excel workbook updated successfully.");
      }
    } catch (e) {
      if (e.status === 409) {
        setConflict(e.detail);
        setError("Synchronization conflict: the Excel file changed since you loaded this record.");
      } else if (e.status === 422) {
        const d = e.detail;
        setError(Array.isArray(d) ? d.join(" ") : typeof d === "string" ? d : JSON.stringify(d));
      } else if (e.status === 423) {
        setError("Excel file is currently being used by another process. Changes cannot be saved until the file becomes available.");
      } else {
        setError(e.message);
      }
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm(`Delete ${form.work_order_id || id} from the Excel workbook? A backup will be created first.`)) return;
    setBusy(true);
    try {
      await api.del(`/api/work-orders/${encodeURIComponent(id)}`);
      nav("/work-orders");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <button className="text-sm text-slate-500 mb-1" onClick={() => nav(-1)}>
            ← Back
          </button>
          <h1 className="text-2xl font-bold tracking-tight">
            {isNew ? "New material request" : `IM WO ${form.work_order_id || id}`}
          </h1>
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <StatusBadge value={form.status} />
            <StatusBadge value={form.priority} />
            <StatusBadge value={form.issue} />
            {form.department && <span className="text-xs text-slate-500">{form.department}</span>}
            {meta?.is_overdue && <StatusBadge value="Overdue" />}
            {meta?.aging_days != null && <span className="text-xs text-slate-500">Age {meta.aging_days} days</span>}
          </div>
        </div>
        <div className="flex gap-2">
          {can("delete") && !isNew && (
            <button className="btn-danger" onClick={remove} disabled={busy}>
              Delete
            </button>
          )}
          {can("edit") && (
            <button className="btn-primary" onClick={() => save(false)} disabled={busy}>
              {busy ? "Saving to Excel…" : "Save to Excel"}
            </button>
          )}
        </div>
      </div>

      {error && <div className="rounded-xl bg-rose-50 text-rose-800 px-4 py-3 text-sm dark:bg-rose-500/10 dark:text-rose-200">{error}</div>}
      {success && <div className="rounded-xl bg-emerald-50 text-emerald-800 px-4 py-3 text-sm dark:bg-emerald-500/10 dark:text-emerald-200">{success}</div>}
      {conflict && (
        <div className="card p-4 border-amber-300">
          <div className="font-semibold mb-2">Conflict warning</div>
          <p className="text-sm text-slate-600 dark:text-slate-300 mb-3">
            The workbook was modified externally. Review the latest Excel values and choose whether to overwrite.
          </p>
          <button className="btn-primary" onClick={() => save(true)}>
            Overwrite Excel with my changes
          </button>
          <button
            className="btn-outline ml-2"
            onClick={() => {
              if (conflict.current) setForm(conflict.current);
              setConflict(null);
            }}
          >
            Load latest Excel values
          </button>
        </div>
      )}

      <div className="card p-5 grid md:grid-cols-2 gap-4">
        {FIELDS.map(([key, label, type, lock]) => (
          <div key={key} className={type === "textarea" ? "md:col-span-2" : ""}>
            <label className="lbl">{label}</label>
            {type === "textarea" ? (
              <textarea rows={3} value={form[key] || ""} onChange={(e) => setField(key, e.target.value)} />
            ) : type === "site" ? (
              <select value={form[key] || ""} onChange={(e) => setField(key, e.target.value)} disabled={!isNew}>
                {(options.department || ["SH5-SH1", "F5"]).map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            ) : ["status", "priority", "assigned_to", "work_type", "issue"].includes(type) ? (
              <select value={form[key] || ""} onChange={(e) => setField(key, e.target.value)}>
                <option value="">—</option>
                {(options[type] || []).map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            ) : type === "datetime" ? (
              <input
                type="datetime-local"
                disabled={lock}
                value={toInput(form[key])}
                onChange={(e) => setField(key, fromInput(e.target.value))}
              />
            ) : (
              <input
                value={form[key] || ""}
                disabled={lock && !isNew}
                onChange={(e) => setField(key, e.target.value)}
              />
            )}
          </div>
        ))}
      </div>
      {!isNew && (
        <p className="text-xs text-slate-400">
          Saving updates the matching row in file.xlsx (SN, due-date and hyperlink formulas are left untouched). A backup is written first.
        </p>
      )}
    </div>
  );
}
