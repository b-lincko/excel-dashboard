import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, qs } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

const EXTRA_KEYS = ["delay_kind", "delay_source", "delay_justification"];
const PENDING_STATUSES = new Set(["open", "under ntp", "on hold"]);
const DUE_OFFSET_FALLBACK = {
  "direct cash": 3,
  "local po": 5,
  international: 10,
  service: 10,
  consumable: 2,
  emergency: 0,
  "under warranty": 10,
  alternative: 10,
};

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
  ["supplier", "Supplier Name", "supplier"],
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
  const { can, user } = useAuth();
  const { toast, ask } = useUi();
  const [form, setForm] = useState({});
  const [original, setOriginal] = useState({});
  const [options, setOptions] = useState({});
  const [syncToken, setSyncToken] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [conflict, setConflict] = useState(null);
  const [busy, setBusy] = useState(false);
  const [meta, setMeta] = useState(null);
  const [history, setHistory] = useState([]);
  const [dueOffsets, setDueOffsets] = useState(DUE_OFFSET_FALLBACK);
  const [addingSupplier, setAddingSupplier] = useState(false);
  const [newSupplier, setNewSupplier] = useState("");
  const [files, setFiles] = useState([]);
  const [fileNote, setFileNote] = useState("");
  const [watching, setWatching] = useState(false);
  const [watchers, setWatchers] = useState([]);
  const [editable, setEditable] = useState(null);
  const [chat, setChat] = useState([]);
  const [chatBody, setChatBody] = useState("");
  const attachRef = useRef(null);

  const dirty = useMemo(() => {
    const keys = [...FIELDS.map(([key]) => key), ...EXTRA_KEYS];
    return keys.some((key) => String(form[key] ?? "") !== String(original[key] ?? ""));
  }, [form, original]);
  const isPending = PENDING_STATUSES.has(String(form.status || "").trim().toLowerCase());
  const dueDays = dueOffsets[String(form.work_type || "").trim().toLowerCase()];
  const readOnly = isNew ? !can("create") : !can("edit");
  const canSave = isNew ? can("create") : can("edit");
  function fieldLocked(key, lock) {
    if (lock || readOnly) return true;
    if (isNew) return false;
    if (!editable) return false;
    return !editable.includes(key);
  }

  useEffect(() => {
    api
      .get("/api/work-orders/options")
      .then((d) => {
        setOptions(d.options || {});
        if (d.due_offsets) setDueOffsets(d.due_offsets);
        if (d.editable_fields) setEditable(d.editable_fields);
      })
      .catch(() => {});
    if (!isNew) {
      api
        .get(`/api/work-orders/${encodeURIComponent(id)}`)
        .then((d) => {
          setForm(d.item);
          setOriginal(d.item);
          setSyncToken(d.sync_token);
          setMeta(d.item);
          const rid = d.item.record_id || id;
          api.get(`/api/work-orders/${encodeURIComponent(rid)}/files`).then((f) => setFiles(f.items || [])).catch(() => {});
          api
            .get(`/api/work-orders/${encodeURIComponent(rid)}/watch`)
            .then((w) => {
              setWatching(!!w.watching);
              setWatchers(w.watchers || []);
            })
            .catch(() => {});
          api
            .get(`/api/work-orders/${encodeURIComponent(rid)}/chat`)
            .then((c) => setChat(c.items || []))
            .catch(() => {});
        })
        .catch((e) => setError(e.message));
    } else {
      const initial = {
        status: "OPEN",
        priority: "MEDIUM",
        created_date: new Date().toISOString().slice(0, 16).replace("T", " "),
        department: "SH5-SH1",
      };
      setForm(initial);
      setOriginal(initial);
    }
  }, [id, isNew]);

  useEffect(() => {
    if (isNew || !form.work_order_id || !can("audit")) return;
    api
      .get(`/api/audit${qs({ work_order_id: form.work_order_id, limit: 25 })}`)
      .then((d) => setHistory(d.items || []))
      .catch(() => {});
  }, [form.work_order_id, isNew, can]);

  useEffect(() => {
    const onLeave = (e) => {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onLeave);
    return () => window.removeEventListener("beforeunload", onLeave);
  }, [dirty]);

  useEffect(() => {
    function onKey(e) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (canSave && !busy) save(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function setField(k, v) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function addSupplier() {
    const name = newSupplier.trim();
    if (!name) return;
    setBusy(true);
    try {
      const d = await api.post("/api/catalog/suppliers", { name });
      const added = d.item?.name || name;
      setOptions((o) => ({
        ...o,
        supplier: Array.from(new Set([...(o.supplier || []), added])).sort((a, b) => a.localeCompare(b)),
      }));
      setField("supplier", added);
      setNewSupplier("");
      setAddingSupplier(false);
      toast(`Supplier “${added}” added`, "success");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
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
        toast("Saved to Excel", "success");
        nav(`/work-orders/${encodeURIComponent(d.item.record_id || d.item.work_order_id)}`);
      } else {
        const skip = new Set([
          "is_closed",
          "is_open",
          "is_status_open",
          "is_placed",
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
        const extraOnly = Object.keys(changes).length > 0 && Object.keys(changes).every((k) => EXTRA_KEYS.includes(k));
        setSuccess(extraOnly ? "Delay notes saved in the app database." : "Excel workbook updated successfully.");
        toast(extraOnly ? "Delay notes saved" : "Excel updated", "success");
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

  async function goBack() {
    if (dirty) {
      const ok = await ask({
        title: "Discard unsaved changes?",
        body: "Edits on this page have not been written to Excel.",
        confirmLabel: "Discard",
        danger: true,
      });
      if (!ok) return;
    }
    nav(-1);
  }

  async function remove() {
    const ok = await ask({
      title: `Delete ${form.work_order_id || id}?`,
      body: "This removes the row from the Excel workbook. A backup is written first.",
      confirmLabel: "Delete from Excel",
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await api.del(`/api/work-orders/${encodeURIComponent(id)}`);
      toast("Deleted from Excel", "success");
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
          <button className="text-sm text-slate-500 mb-1" onClick={goBack}>
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
            {dirty && <span className="text-xs text-amber-700 dark:text-amber-300">Unsaved changes</span>}
          </div>
        </div>
        <div className="flex gap-2">
          {!isNew && (
            <button
              className="btn-outline"
              onClick={() => api.download(`/api/work-orders/${encodeURIComponent(id)}/sheet`, `WO_${form.work_order_id || id}.pdf`)}
            >
              Print sheet
            </button>
          )}
          {!isNew && (
            <button
              className="btn-outline"
              onClick={async () => {
                const rid = form.record_id || id;
                const d = watching
                  ? await api.del(`/api/work-orders/${encodeURIComponent(rid)}/watch`)
                  : await api.post(`/api/work-orders/${encodeURIComponent(rid)}/watch`);
                setWatching(!!d.watching);
                setWatchers(d.watchers || []);
                toast(d.watching ? "Following this MR" : "Unfollowed", "success");
              }}
            >
              {watching ? "Following" : "Follow"}
              {watchers.length ? ` · ${watchers.length}` : ""}
            </button>
          )}
          {can("delete") && !isNew && (
            <button className="btn-danger" onClick={remove} disabled={busy}>
              Delete
            </button>
          )}
          {canSave && (
            <button className="btn-primary" onClick={() => save(false)} disabled={busy || (!isNew && !dirty)}>
              {busy ? "Saving…" : isNew ? "Create in Excel" : "Save to Excel"}
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
              <>
                <textarea rows={3} value={form[key] || ""} disabled={fieldLocked(key)} onChange={(e) => setField(key, e.target.value)} />
                {key === "remarks" && (
                  <p className="text-[11px] text-slate-500 mt-1">Type @username in remarks to ping that person. Followers are notified on save.</p>
                )}
              </>
            ) : type === "site" ? (
              <select value={form[key] || ""} onChange={(e) => setField(key, e.target.value)} disabled={!isNew || readOnly}>
                {(options.department || ["SH5-SH1", "F5"]).map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            ) : type === "supplier" ? (
              <div className="space-y-2">
                <select value={form.supplier || ""} disabled={fieldLocked("supplier")} onChange={(e) => setField("supplier", e.target.value)}>
                  <option value="">—</option>
                  {(options.supplier || []).map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
                {!fieldLocked("supplier") && !addingSupplier && (
                  <button type="button" className="btn-outline !py-1 !px-2 text-xs" onClick={() => setAddingSupplier(true)}>
                    + Add supplier
                  </button>
                )}
                {addingSupplier && !fieldLocked("supplier") && (
                  <div className="flex gap-2">
                    <input
                      value={newSupplier}
                      onChange={(e) => setNewSupplier(e.target.value)}
                      placeholder="New supplier name"
                      autoFocus
                    />
                    <button type="button" className="btn-primary !py-1 !px-2 text-xs" onClick={addSupplier} disabled={busy}>
                      Add
                    </button>
                    <button type="button" className="btn-outline !py-1 !px-2 text-xs" onClick={() => setAddingSupplier(false)}>
                      Cancel
                    </button>
                  </div>
                )}
              </div>
            ) : ["status", "priority", "assigned_to", "work_type", "issue"].includes(type) ? (
              <select value={form[key] || ""} disabled={fieldLocked(key)} onChange={(e) => setField(key, e.target.value)}>
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
                disabled={fieldLocked(key, lock)}
                value={toInput(form[key])}
                onChange={(e) => setField(key, fromInput(e.target.value))}
              />
            ) : (
              <input
                value={form[key] || ""}
                disabled={(lock && !isNew) || fieldLocked(key)}
                onChange={(e) => setField(key, e.target.value)}
              />
            )}
            {key === "due_date" && (
              <p className="text-[11px] text-slate-500 mt-1">
                {dueDays != null
                  ? `From purchase type “${form.work_type || "—"}”: +${dueDays} day${dueDays === 1 ? "" : "s"} after MR received. Excel formula is not overwritten.`
                  : "Direct Cash +3, Local PO +5, International +10, Service +10, Consumable +2, Emergency +0, Under Warranty +10, Alternative +10."}
              </p>
            )}
          </div>
        ))}
      </div>
      {isPending && (
        <div className="card p-5 space-y-3">
          <div>
            <div className="font-semibold">Delay (pending only)</div>
            <p className="text-xs text-slate-500">
              Placement delay, delivery delay and justification. Source: site, procurement or supplier. Stored in the app database, not Excel.
            </p>
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="lbl">Delay type</label>
              <select value={form.delay_kind || ""} disabled={fieldLocked("delay_kind")} onChange={(e) => setField("delay_kind", e.target.value)}>
                <option value="">—</option>
                <option value="placement">Placement delay</option>
                <option value="delivery">Delivery delay</option>
              </select>
            </div>
            <div>
              <label className="lbl">Delay source</label>
              <select value={form.delay_source || ""} disabled={fieldLocked("delay_source")} onChange={(e) => setField("delay_source", e.target.value)}>
                <option value="">—</option>
                <option value="site">Site</option>
                <option value="procurement">Procurement</option>
                <option value="supplier">Supplier</option>
              </select>
            </div>
            <div className="md:col-span-2">
              <label className="lbl">Delay justification</label>
              <textarea
                rows={3}
                value={form.delay_justification || ""}
                disabled={fieldLocked("delay_justification")}
                onChange={(e) => setField("delay_justification", e.target.value)}
              />
            </div>
          </div>
        </div>
      )}
      {!isNew && (
        <div className="card p-5 space-y-3">
          <div>
            <div className="font-semibold">Work-order chat</div>
            <p className="text-xs text-slate-500">Thread is tied to this MR. Followers and @mentions are notified. Messages stay in the app, not Excel.</p>
          </div>
          <div className="max-h-64 overflow-y-auto space-y-2">
            {chat.map((m) => (
              <div key={m.id} className={`text-sm ${m.username === user?.username ? "text-right" : ""}`}>
                <div className="text-[11px] text-slate-500">
                  {m.username} · {m.created_at}
                </div>
                <div className={`inline-block rounded-2xl px-3 py-1.5 whitespace-pre-wrap ${m.username === user?.username ? "bg-brand-700 text-white" : "bg-slate-100 dark:bg-white/5"}`}>
                  {m.body}
                </div>
              </div>
            ))}
            {!chat.length && <div className="text-sm text-slate-500">No messages yet.</div>}
          </div>
          <form
            className="flex gap-2"
            onSubmit={async (e) => {
              e.preventDefault();
              const text = chatBody.trim();
              if (!text) return;
              try {
                const d = await api.post(`/api/work-orders/${encodeURIComponent(id)}/chat`, { body: text });
                setChat((prev) => [...prev, d.item]);
                setChatBody("");
              } catch (err) {
                setError(err.message);
              }
            }}
          >
            <input value={chatBody} onChange={(e) => setChatBody(e.target.value)} placeholder="Message this MR… @username to ping" autoComplete="off" />
            <button className="btn-primary" disabled={!chatBody.trim()}>
              Send
            </button>
          </form>
        </div>
      )}
      {!isNew && (
        <div className="card p-5 space-y-3">
          <div>
            <div className="font-semibold">Attachments</div>
            <p className="text-xs text-slate-500">PDFs and screenshots stay in the app database, not Excel. They can be linked to this work order or a remark note.</p>
          </div>
          <ul className="space-y-2">
            {files.map((f) => (
              <li key={f.id} className="flex items-center justify-between gap-3 text-sm">
                <div className="min-w-0">
                  <button className="text-brand-700 hover:underline truncate" type="button" onClick={() => api.download(`/api/files/${f.id}`, f.filename)}>
                    {f.filename}
                  </button>
                  <div className="text-[11px] text-slate-500">
                    {f.kind} · {f.created_by} · {f.created_at}
                    {f.note ? ` · ${f.note}` : ""}
                  </div>
                </div>
                {can("edit") && (
                  <button
                    type="button"
                    className="btn-outline !py-1 !px-2 text-xs"
                    onClick={async () => {
                      await api.del(`/api/files/${f.id}`);
                      setFiles((prev) => prev.filter((x) => x.id !== f.id));
                    }}
                  >
                    Remove
                  </button>
                )}
              </li>
            ))}
            {!files.length && <li className="text-sm text-slate-500">No files yet.</li>}
          </ul>
          {can("edit") && (
            <div className="space-y-2">
              <input value={fileNote} onChange={(e) => setFileNote(e.target.value)} placeholder="Optional remark / caption" />
              <input
                ref={attachRef}
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,application/pdf,image/*"
                className="hidden"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (!file) return;
                  const fd = new FormData();
                  fd.append("file", file);
                  fd.append("note", fileNote);
                  try {
                    const d = await api.upload(`/api/work-orders/${encodeURIComponent(id)}/files`, fd);
                    setFiles((prev) => [d.item, ...prev]);
                    setFileNote("");
                    toast("File attached", "success");
                  } catch (err) {
                    setError(err.message);
                  }
                }}
              />
              <button type="button" className="btn-outline" onClick={() => attachRef.current?.click()}>
                Attach PDF or screenshot
              </button>
            </div>
          )}
        </div>
      )}
      {!isNew && (
        <p className="text-xs text-slate-400">
          Saving updates the matching row in file.xlsx (SN, due-date and hyperlink formulas are left untouched). Delay notes stay in the app database. A backup is written first. Ctrl/⌘+S to save.
        </p>
      )}
      {!isNew && can("audit") && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 font-semibold">Recent changes</div>
          {history.length ? (
            <table className="data">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>User</th>
                  <th>Field</th>
                  <th>Old</th>
                  <th>New</th>
                </tr>
              </thead>
              <tbody>
                {history.map((r) => (
                  <tr key={r.id} className="!cursor-default">
                    <td className="font-mono text-xs">{r.created_at}</td>
                    <td>{r.username}</td>
                    <td>{r.field || r.action}</td>
                    <td className="max-w-[200px] truncate text-slate-500">{r.old_value}</td>
                    <td className="max-w-[200px] truncate">{r.new_value || r.details}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="px-4 pb-4 text-sm text-slate-500">No audit events for this work order yet.</div>
          )}
        </div>
      )}
    </div>
  );
}
