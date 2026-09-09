import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, qs } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import MentionBox from "../components/MentionBox.jsx";
import TypeAhead from "../components/TypeAhead.jsx";


const EXTRA_KEYS = ["delay_kind", "delay_source", "delay_justification", "unit_price", "price", "total_price", "final_price"];
const DELAY_OPEN = new Set(["open"]);
const DELAY_PENDING = new Set(["pending"]);
const DELAY_NEVER = new Set(["closed", "close", "placed", "estimation price", "delivered material inspection"]);
const SHEET_SITES = ["SH5-SH1", "F5", "Office", "Accommodations"];
const FALLBACK_CAMPS = [
  { id: "SH5-S1", label: "Site - 1", group: "SH5", sheet: "SH5-SH1" },
  { id: "SH5-S2", label: "Site - 2", group: "SH5", sheet: "SH5-SH1" },
  { id: "SH5-S3", label: "Site - 3", group: "SH5", sheet: "SH5-SH1" },
  { id: "SH5-S4A", label: "Site - 4A", group: "SH5", sheet: "SH5-SH1" },
  { id: "SH5-S5", label: "Site - 5", group: "SH5", sheet: "SH5-SH1" },
  { id: "SH5-S7", label: "Site - 7", group: "SH5", sheet: "SH5-SH1" },
  { id: "SH1-L1", label: "L1", group: "SH1", sheet: "SH5-SH1" },
  { id: "SH1-L2", label: "L2", group: "SH1", sheet: "SH5-SH1" },
  { id: "SH1-L3", label: "L3", group: "SH1", sheet: "SH5-SH1" },
  { id: "SH1-L4", label: "L4", group: "SH1", sheet: "SH5-SH1" },
  { id: "SH1-L5", label: "L5", group: "SH1", sheet: "SH5-SH1" },
  { id: "SH1-L7", label: "L7", group: "SH1", sheet: "SH5-SH1" },
  { id: "SH1-LS1", label: "LS1", group: "SH1", sheet: "SH5-SH1" },
  { id: "SH1-LS2", label: "LS2", group: "SH1", sheet: "SH5-SH1" },
];

function duePassed(value) {
  if (!value) return false;
  const due = new Date(String(value).replace(" ", "T"));
  if (Number.isNaN(due.getTime())) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  due.setHours(0, 0, 0, 0);
  return due < today;
}

function canAddDelay(form) {
  const st = String(form.status || "").trim().toLowerCase();
  if (!st || DELAY_NEVER.has(st)) return false;
  if (DELAY_PENDING.has(st)) return true;
  if (DELAY_OPEN.has(st)) return duePassed(form.due_date);
  return false;
}
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
  ["due_date", "Due date", "due"],
  ["completion_date", "IM WO Completion", "datetime"],
  ["scheduled_date", "Date of PO / Expected PO / RFQ Sent", "datetime"],
  ["closed_date", "ETA / Expected RFQ Response", "datetime"],
  ["supplier", "Supplier Name", "supplier"],
  ["po_number", "PO NO #", "text"],
  ["issue", "Delivery Status", "issue"],
  ["description", "Required Material Details", "textarea"],
  ["remarks", "REMARKS / NOTES", "textarea"],
];

const FIELD_MAP = Object.fromEntries(FIELDS.map((row) => [row[0], row]));
const GROUPS = [
  {
    id: "request",
    title: "Request",
    hint: "Who needs what, and by when.",
    keys: ["work_order_id", "department", "status", "priority", "assigned_to", "work_type", "location", "created_date", "due_date"],
  },
  {
    id: "buy",
    title: "Procurement",
    hint: "PO and expected dates. Suppliers live in the items list above.",
    keys: ["po_number", "scheduled_date", "closed_date"],
  },
  {
    id: "ship",
    title: "Delivery",
    hint: "What arrived, and the running notes.",
    keys: ["issue", "completion_date", "remarks"],
  },
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
  const people = options.mention_users || [];
  const [files, setFiles] = useState([]);
  const [fileNote, setFileNote] = useState("");
  const [watching, setWatching] = useState(false);
  const [watchers, setWatchers] = useState([]);
  const [editable, setEditable] = useState(null);
  const [chat, setChat] = useState([]);
  const [chatThread, setChatThread] = useState(null);
  const [chatBody, setChatBody] = useState("");
  const [timeline, setTimeline] = useState([]);
  const [remarkRules, setRemarkRules] = useState(["*->ON HOLD", "*->CLOSED"]);
  const [tab, setTab] = useState("details");
  const [others, setOthers] = useState([]);
  const [closeOpen, setCloseOpen] = useState(false);
  const [closeForm, setCloseForm] = useState({ remark: "", unit_price: "", price: "", total_price: "", final_price: "" });
  const attachRef = useRef(null);

  const dirty = useMemo(() => {
    const keys = [...FIELDS.map(([key]) => key), ...EXTRA_KEYS, "camp_site"];
    const fieldsDirty = keys.some((key) => String(form[key] ?? "") !== String(original[key] ?? ""));
    const linesDirty = JSON.stringify(form.lines || []) !== JSON.stringify(original.lines || []);
    return fieldsDirty || linesDirty;
  }, [form, original]);
  const showDelay = canAddDelay(form);
  const dueDays = dueOffsets[String(form.work_type || "").trim().toLowerCase()];
  const readOnly = isNew ? !can("create") : !can("edit");
  const canSave = isNew ? can("create") : can("edit");
  const poLocked = !!(form.po_approval?.locked || form.po_approval?.state === "approved" || form.po_approval?.state === "sent_to_accounts");
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
        setOptions({ ...(d.options || {}), camp_sites: d.camp_sites || d.options?.camp_sites || [] });
        if (d.due_offsets) setDueOffsets(d.due_offsets);
        if (d.editable_fields) setEditable(d.editable_fields);
        if (d.status_change_remarks) setRemarkRules(d.status_change_remarks);
      })
      .catch(() => {});
    if (!isNew) {
      api
        .get(`/api/work-orders/${encodeURIComponent(id)}`)
        .then((d) => {
          const item = { ...d.item, lines: d.item.lines || [] };
          setForm(item);
          setOriginal(item);
          setSyncToken(d.sync_token);
          setMeta(item);
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
            .then((c) => {
              setChat(c.items || []);
              setChatThread(c.thread || null);
            })
            .catch(() => {});
          api
            .get(`/api/work-orders/${encodeURIComponent(rid)}/timeline`)
            .then((t) => setTimeline(t.items || []))
            .catch(() => {});
        })
        .catch((e) => setError(e.message));
    } else {
      const initial = {
        status: "OPEN",
        priority: "MEDIUM",
        created_date: new Date().toISOString().slice(0, 16).replace("T", " "),
        department: "SH5-SH1",
        lines: [{ supplier: "", material: "", qty: "", unit: "", notes: "", needed_date: "" }],
      };
      setForm(initial);
      setOriginal(initial);
    }
    setTab("details");
  }, [id, isNew]);

  useEffect(() => {
    if (isNew || !id) {
      setOthers([]);
      return undefined;
    }
    function beat() {
      api
        .post(`/api/work-orders/${encodeURIComponent(id)}/presence`)
        .then((d) => setOthers(d.others || []))
        .catch(() => {});
    }
    beat();
    const timer = window.setInterval(beat, 15000);
    return () => window.clearInterval(timer);
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

  async function save(force = false) {
    setBusy(true);
    setError("");
    setSuccess("");
    setConflict(null);
    try {
      if (isNew) {
        const d = await api.post("/api/work-orders", { data: form });
        setSuccess("Material request saved in the database. Excel updates at midnight.");
        toast("Saved", "success");
        nav(`/work-orders/${encodeURIComponent(d.item.record_id || d.item.work_order_id)}`);
      } else {
        const skip = new Set([
          "is_closed",
          "is_open",
          "is_status_open",
          "is_placed",
          "is_overdue",
          "is_delayed",
          "is_pending",
          "is_in_progress",
          "is_ntp",
          "is_on_hold",
          "is_delivered",
          "is_pending_po",
          "is_awaiting_po",
          "is_need_rfq",
          "is_rfq_sent",
          "is_po_issued",
          "is_eta_late",
          "is_due_this_week",
          "is_due_soon",
          "days_until_due",
          "days_to_eta",
          "on_time",
          "po_stage",
          "aging_days",
          "closing_days",
          "days_overdue",
          "open_reason",
          "record_id",
          "lines",
          "camp_site_label",
          "site_group",
          "site_display",
        ]);
        const changes = {};
        Object.keys(form).forEach((k) => {
          if (k.startsWith("_") || skip.has(k)) return;
          if (String(form[k] ?? "") !== String(original[k] ?? "")) changes[k] = form[k];
        });
        if (JSON.stringify(form.lines || []) !== JSON.stringify(original.lines || [])) {
          changes.lines = form.lines || [];
        }
        const d = await api.put(`/api/work-orders/${encodeURIComponent(id)}`, {
          changes,
          sync_token: syncToken,
          force,
        });
        setForm(d.item);
        setOriginal(d.item);
        setMeta(d.item);
        setSyncToken(d.sync_token);
        const keys = Object.keys(changes);
        const extraOnly = keys.length > 0 && keys.every((k) => EXTRA_KEYS.includes(k));
        const appOnly = keys.length > 0 && keys.every((k) => EXTRA_KEYS.includes(k) || k === "camp_site");
        const linesOnly = keys.length > 0 && keys.every((k) => k === "lines" || EXTRA_KEYS.includes(k));
        setSuccess(
          extraOnly
            ? "Delay notes saved in the app database."
            : appOnly
              ? "Camp site saved in the app database."
              : linesOnly
                ? "Supplier line items saved in the app database. Excel still has one supplier cell and one material cell."
                : "Saved in the database. Excel updates at midnight."
        );
        toast(extraOnly ? "Delay notes saved" : appOnly ? "Camp site saved" : linesOnly ? "Line items saved" : "Saved", "success");
      }
    } catch (e) {
      if (e.status === 409) {
        setConflict(e.detail);
        setError("This record changed since you opened it. Reload or overwrite.");
      } else if (e.status === 422) {
        const d = e.detail;
        setError(Array.isArray(d) ? d.join(" ") : typeof d === "string" ? d : JSON.stringify(d));
      } else {
        setError(e.message);
      }
    } finally {
      setBusy(false);
    }
  }

  function goBack() {
    nav(-1);
  }

  async function remove() {
    const ok = await ask({
      title: `Delete ${form.work_order_id || id}?`,
      body: "This removes the work order from the database. Excel is updated at midnight.",
      confirmLabel: "Delete",
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await api.del(`/api/work-orders/${encodeURIComponent(id)}`);
      toast("Deleted", "success");
      nav("/work-orders");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function openClose() {
    setError("");
    setCloseForm({
      remark: "",
      unit_price: form.unit_price || "",
      price: form.price || "",
      total_price: form.total_price || "",
      final_price: form.final_price || "",
    });
    setCloseOpen(true);
  }

  async function closeOrder() {
    setError("");
    const needsRemark = (remarkRules || []).some((rule) => String(rule || "").toUpperCase().includes("CLOSED"));
    const remark = String(closeForm.remark || "").trim();
    if (needsRemark && !remark) {
      setError("A remark is required to close.");
      return;
    }
    setBusy(true);
    try {
      const d = await api.post(`/api/work-orders/${encodeURIComponent(form.record_id || id)}/close`, {
        remark,
        unit_price: closeForm.unit_price,
        price: closeForm.price,
        total_price: closeForm.total_price,
        final_price: closeForm.final_price,
      });
      setForm(d.item);
      setOriginal(d.item);
      setMeta(d.item);
      setSyncToken(d.sync_token || syncToken);
      setCloseOpen(false);
      setSuccess(d.already ? "Already closed." : "Closed.");
      toast(d.already ? "Already closed" : "Closed", "success");
    } catch (e) {
      const d = e.detail;
      setError(Array.isArray(d) ? d.join(" ") : typeof d === "string" ? d : e.message);
    } finally {
      setBusy(false);
    }
  }

  const lineCount = Array.isArray(form.lines) ? form.lines.filter((l) => l.supplier || l.material).length : 0;
  const nextHint = !isNew && !form.work_order_id
    ? ""
    : !form.assigned_to
    ? "Unassigned — claim it or pick a technician."
    : meta?.is_overdue
      ? "Past due — update status, delivery, or add a delay note."
      : String(form.status || "").toUpperCase() === "OPEN" && !form.supplier
        ? "Still open — add a supplier or place the PO."
        : dirty
          ? "Unsaved changes."
          : "";

  function renderField(key) {
    const spec = FIELD_MAP[key];
    if (!spec) return null;
    const [, label, type, lock] = spec;
    return (
      <div key={key} className={type === "textarea" ? "md:col-span-2" : ""}>
        <label className="lbl">{label}</label>
        {type === "textarea" ? (
          <>
            {key === "remarks" ? (
              <>
                <MentionBox
                  rows={3}
                  value={form[key] || ""}
                  disabled={fieldLocked(key)}
                  people={people}
                  onChange={(v) => setField(key, v)}
                  placeholder="Notes… type @ to mention a user"
                />
                <p className="text-[11px] text-slate-500 mt-1">Type @ to pick a username. Followers are notified on save.</p>
              </>
            ) : (
              <textarea rows={3} value={form[key] || ""} disabled={fieldLocked(key)} onChange={(e) => setField(key, e.target.value)} />
            )}
          </>
        ) : type === "site" ? (
          <select
            value={form.camp_site || form.department || ""}
            disabled={readOnly}
            onChange={(e) => {
              const id = e.target.value;
              const camps = options.camp_sites?.length ? options.camp_sites : FALLBACK_CAMPS;
              const camp = camps.find((c) => c.id === id || c.label === id);
              if (camp) {
                setForm((f) => ({
                  ...f,
                  camp_site: camp.id,
                  department: isNew ? camp.sheet || "SH5-SH1" : f.department || camp.sheet || "SH5-SH1",
                }));
              } else {
                setForm((f) => ({
                  ...f,
                  camp_site: "",
                  department: isNew ? id : f.department,
                }));
              }
            }}
          >
            <option value="SH5-SH1">SH5-SH1 (unspecified)</option>
            {["SH5", "SH1"].map((g) => (
              <optgroup key={g} label={g}>
                {(options.camp_sites?.length ? options.camp_sites : FALLBACK_CAMPS)
                  .filter((c) => c.group === g)
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.label}
                    </option>
                  ))}
              </optgroup>
            ))}
            {SHEET_SITES.filter((s) => s !== "SH5-SH1").map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        ) : type === "assigned_to" ? (
          <TypeAhead
            value={form[key] || ""}
            disabled={fieldLocked(key)}
            options={
              form.assigned_to && !(options.assigned_to || []).includes(form.assigned_to)
                ? [form.assigned_to, ...(options.assigned_to || [])]
                : options.assigned_to || []
            }
            allowCustom={false}
            placeholder="Pick a technician"
            onChange={(v) => setField(key, v)}
          />
        ) : ["status", "priority", "work_type", "issue"].includes(type) ? (
          <select value={form[key] || ""} disabled={fieldLocked(key)} onChange={(e) => setField(key, e.target.value)}>
            <option value="">—</option>
            {form[key] && !(options[type] || []).includes(form[key]) && <option value={form[key]}>{form[key]}</option>}
            {(options[type] || []).map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        ) : type === "due" ? (
          String(form.work_type || "").trim() ? (
            <input type="date" disabled value={(form.due_date || "").slice(0, 10)} />
          ) : (
            <input
              type="date"
              disabled={fieldLocked(key)}
              value={(form.due_date || "").slice(0, 10)}
              onChange={(e) => setField(key, e.target.value)}
            />
          )
        ) : type === "datetime" ? (
          <input
            type="datetime-local"
            disabled={fieldLocked(key, lock)}
            value={toInput(form[key])}
            onChange={(e) => setField(key, fromInput(e.target.value))}
          />
        ) : (
          <input value={form[key] || ""} disabled={(lock && !isNew) || fieldLocked(key)} onChange={(e) => setField(key, e.target.value)} />
        )}
        {key === "status" && (remarkRules || []).length > 0 && (
          <p className="text-[11px] text-slate-500 mt-1">
            Transitions that need a remark: {(remarkRules || []).join(", ")}.
          </p>
        )}
        {key === "due_date" && (
          <p className="text-[11px] text-slate-500 mt-1">
            {String(form.work_type || "").trim()
              ? dueDays != null
                ? `From “${form.work_type}”: +${dueDays} day${dueDays === 1 ? "" : "s"} after MR received.`
                : "Due date follows this purchase type."
              : "Purchase type is empty — pick the due date yourself (date only)."}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-4 pb-8">
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
            {(form.site_display || form.camp_site_label || form.department) && (
              <span className="text-xs text-slate-500">{form.site_display || form.camp_site_label || form.department}</span>
            )}
            {meta?.is_overdue && <StatusBadge value="Overdue" />}
            {meta?.aging_days != null && <span className="text-xs text-slate-500">Age {meta.aging_days} days</span>}
            {dirty && <span className="text-xs text-amber-700 dark:text-amber-300">Unsaved</span>}
          </div>
          {nextHint && <p className="text-sm text-slate-500 mt-2">{nextHint}</p>}
          {others.length > 0 && (
            <p className="text-xs text-sky-700 dark:text-sky-300 mt-2" data-tour="presence">
              Also here: {others.map((p) => p.full_name || p.username).join(", ")}
            </p>
          )}
        </div>
        <div className="flex gap-2 flex-wrap justify-end">
          {isNew && canSave && (
            <button className="btn-primary" onClick={() => save(false)} disabled={busy}>
              {busy ? "Saving…" : "Create request"}
            </button>
          )}
          {!isNew && (
            <button
              className="btn-outline"
              onClick={() => api.download(`/api/work-orders/${encodeURIComponent(id)}/sheet`, `WO_${form.work_order_id || id}.pdf`)}
            >
              Print
            </button>
          )}
          {!isNew && can("edit") && !fieldLocked("assigned_to") && (
            <button
              className="btn-outline"
              disabled={busy}
              onClick={async () => {
                const rid = form.record_id || id;
                try {
                  const d = await api.post(`/api/work-orders/${encodeURIComponent(rid)}/claim`);
                  setForm(d.item);
                  setOriginal(d.item);
                  setMeta(d.item);
                  toast(d.already ? "Already claimed" : "Claimed", "success");
                } catch (e) {
                  if (e.status === 409) {
                    const ok = await ask({
                      title: "Already assigned",
                      body: e.detail?.message || e.message,
                      confirmLabel: "Take over",
                      danger: true,
                    });
                    if (!ok) return;
                    const d = await api.post(`/api/work-orders/${encodeURIComponent(rid)}/claim?force=true`);
                    setForm(d.item);
                    setOriginal(d.item);
                    setMeta(d.item);
                    toast("Taken over", "success");
                    return;
                  }
                  setError(e.message);
                }
              }}
            >
              Claim
            </button>
          )}
          {!isNew && can("edit") && !form.is_closed && (
            <button className="btn-outline" disabled={busy} onClick={openClose}>
              Close order
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
        </div>
      </div>

      {error && <div className="rounded-xl bg-rose-50 text-rose-800 px-4 py-3 text-sm dark:bg-rose-500/10 dark:text-rose-200">{error}</div>}
      {success && <div className="rounded-xl bg-emerald-50 text-emerald-800 px-4 py-3 text-sm dark:bg-emerald-500/10 dark:text-emerald-200">{success}</div>}
      {conflict && (
        <div className="card p-4 border-amber-300">
          <div className="font-semibold mb-2">Record changed</div>
          <p className="text-sm text-slate-600 dark:text-slate-300 mb-3">
            Someone else saved this material request. Reload their values or overwrite with yours.
          </p>
          <button className="btn-primary" onClick={() => save(true)}>
            Overwrite with my changes
          </button>
          <button
            className="btn-outline ml-2"
            onClick={() => {
              if (conflict.current) setForm(conflict.current);
              setConflict(null);
            }}
          >
            Load latest
          </button>
        </div>
      )}

      {!isNew && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          <div className="stat-tile">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">Assigned</div>
            <div className="text-sm font-semibold truncate">{form.assigned_to || "—"}</div>
          </div>
          <div className="stat-tile">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">Due</div>
            <div className={`text-sm font-semibold truncate ${meta?.is_overdue ? "text-rose-600" : ""}`}>{(form.due_date || "").slice(0, 10) || "—"}</div>
          </div>
          <div className="stat-tile">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">Supplier</div>
            <div className="text-sm font-semibold truncate">{form.supplier || "—"}</div>
          </div>
          <div className="stat-tile">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">PO</div>
            <div className="text-sm font-semibold truncate">{form.po_number || "—"}</div>
          </div>
          <div className="stat-tile">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">Delivery</div>
            <div className="text-sm font-semibold truncate">{form.issue || "—"}</div>
          </div>
        </div>
      )}

      <div className="tab-bar" data-tour="wo-tabs">
        <button type="button" className={`tab-btn ${tab === "details" ? "is-on" : ""}`} onClick={() => setTab("details")}>
          Details
        </button>
        <button type="button" className={`tab-btn ${tab === "lines" ? "is-on" : ""}`} onClick={() => setTab("lines")}>
          Items{lineCount ? ` · ${lineCount}` : ""}
        </button>
        {!isNew && (
          <button type="button" className={`tab-btn ${tab === "activity" ? "is-on" : ""}`} onClick={() => setTab("activity")}>
            Activity{chat.length || files.length ? ` · ${chat.length + files.length}` : ""}
          </button>
        )}
        {!isNew && (
          <Link className="tab-btn" to={`/approvals?id=${encodeURIComponent(form.record_id || id)}`}>
            PO signatures
          </Link>
        )}
      </div>

      {tab === "details" && (
        <div className="space-y-4">
          {GROUPS.map((group) => (
            <div key={group.id}>
              {group.id === "buy" && (
                <div className="space-y-4">
                  <LineItemsCard
                    form={form}
                    setForm={setForm}
                    options={options}
                    readOnly={readOnly}
                    supplierLocked={fieldLocked("supplier")}
                  />
                  <div className="card p-5 space-y-3">
                    <div>
                      <div className="font-semibold">Material notes</div>
                      <p className="text-xs text-slate-500">
                        Excel keeps one material cell. Leave this blank and it is filled from the items above (item 1, item 2, …).
                      </p>
                    </div>
                    <div className="grid md:grid-cols-2 gap-4">{renderField("description")}</div>
                  </div>
                </div>
              )}
              <div className="card p-5 space-y-3">
                <div>
                  <div className="font-semibold">{group.title}</div>
                  <p className="text-xs text-slate-500">{group.hint}</p>
                </div>
                <div className="grid md:grid-cols-2 gap-4">{group.keys.map(renderField)}</div>
              </div>
            </div>
          ))}
          {showDelay && (
            <div className="card p-5 space-y-3">
              <div>
                <div className="font-semibold">Delay</div>
                <p className="text-xs text-slate-500">Open past due date, or Pending. Closed, Placed, Estimation Price and Delivered Material Inspection are not delays.</p>
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
                  <textarea rows={3} value={form.delay_justification || ""} disabled={fieldLocked("delay_justification")} onChange={(e) => setField("delay_justification", e.target.value)} />
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "lines" && (
        <LineItemsCard
          form={form}
          setForm={setForm}
          options={options}
          readOnly={readOnly || poLocked}
          supplierLocked={fieldLocked("supplier")}
        />
      )}

      {tab === "activity" && !isNew && (
        <div className="space-y-4">
          <div className="card p-5 space-y-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="font-semibold">Chat</div>
                <p className="text-xs text-slate-500">Tied to this MR. Opens only when you send a message. Followers and @mentions are notified.</p>
              </div>
              {chatThread && (
                <button
                  type="button"
                  className="btn-ghost !px-2 !py-1 text-xs"
                  onClick={async () => {
                    const ok = await ask({
                      title: "Clear this chat?",
                      body: "Messages on this MR are removed. Send again to continue.",
                      confirmLabel: "Clear chat",
                      danger: true,
                    });
                    if (!ok) return;
                    await api.del(`/api/chat/threads/${chatThread.id}/messages`);
                    setChat([]);
                    toast("Chat cleared", "success");
                  }}
                >
                  Clear chat
                </button>
              )}
            </div>
            <div className="max-h-64 overflow-y-auto space-y-2">
              {chat.map((m) => (
                <div key={m.id} className={`text-sm group ${m.username === user?.username ? "text-right" : ""}`}>
                  <div className="text-[11px] text-slate-500">
                    {m.username} · {m.created_at}
                    {(m.username === user?.username || user?.role === "admin") && chatThread && (
                      <button
                        type="button"
                        className="ml-2 text-rose-600 opacity-0 group-hover:opacity-100"
                        onClick={async () => {
                          await api.del(`/api/chat/threads/${chatThread.id}/messages/${m.id}`);
                          setChat((prev) => prev.filter((x) => x.id !== m.id));
                        }}
                      >
                        Delete
                      </button>
                    )}
                  </div>
                  <div className={`inline-block rounded-2xl px-3 py-1.5 whitespace-pre-wrap ${m.username === user?.username ? "bg-brand-700 text-white" : "bg-slate-100 dark:bg-white/5"}`}>
                    {m.body}
                  </div>
                </div>
              ))}
              {!chat.length && <div className="text-sm text-slate-500">No messages yet. Send one to start this conversation.</div>}
            </div>
            <form
              className="flex gap-2"
              onSubmit={async (e) => {
                e.preventDefault();
                const textBody = chatBody.trim();
                if (!textBody) return;
                try {
                  const d = await api.post(`/api/work-orders/${encodeURIComponent(id)}/chat`, { body: textBody });
                  setChat((prev) => [...prev, d.item]);
                  if (d.thread) setChatThread(d.thread);
                  setChatBody("");
                  api.get(`/api/work-orders/${encodeURIComponent(id)}/timeline`).then((t) => setTimeline(t.items || [])).catch(() => {});
                } catch (err) {
                  setError(err.message);
                }
              }}
            >
              <MentionBox value={chatBody} onChange={setChatBody} people={people} placeholder="Message this MR… type @ to mention" className="flex-1" />
              <button className="btn-primary" disabled={!chatBody.trim()}>
                Send
              </button>
            </form>
          </div>
          <div className="card p-5 space-y-3">
            <div>
              <div className="font-semibold">Attachments</div>
              <p className="text-xs text-slate-500">PDFs and screenshots stay with this record.</p>
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
                <input value={fileNote} onChange={(e) => setFileNote(e.target.value)} placeholder="Optional caption" />
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
          <div className="card overflow-hidden">
            <div className="px-4 py-3">
              <div className="font-semibold">Timeline</div>
              <p className="text-xs text-slate-500">Field changes, chat, files, follows and seen.</p>
            </div>
            <div className="max-h-80 overflow-y-auto divide-y divide-slate-100 dark:divide-white/5">
              {(timeline.length ? timeline : history.map((r) => ({ kind: "field", at: r.created_at, ...r }))).map((ev, i) => (
                <div key={`${ev.kind}-${ev.at}-${i}`} className="px-4 py-2 text-sm">
                  <div className="text-[11px] text-slate-500">
                    {ev.at} · {ev.username || "—"} · {ev.kind}
                  </div>
                  <div>
                    {ev.kind === "chat"
                      ? ev.body
                      : ev.kind === "file"
                        ? `Attached ${ev.filename || "file"}${ev.note ? ` — ${ev.note}` : ""}`
                        : ev.kind === "follow"
                          ? "Started following"
                          : ev.kind === "seen"
                            ? "Marked seen"
                            : `${ev.field || ev.action || "update"}${ev.old_value || ev.new_value ? `: ${ev.old_value || "—"} → ${ev.new_value || ev.details || "—"}` : ""}`}
                  </div>
                </div>
              ))}
              {!timeline.length && !history.length && <div className="px-4 py-6 text-sm text-slate-500">No events yet.</div>}
            </div>
          </div>
        </div>
      )}

      {closeOpen && (
        <div className="fixed inset-0 z-40 bg-black/40 grid place-items-center p-4">
          <div className="card p-5 w-full max-w-lg space-y-3">
            <div className="font-semibold">Close this material request?</div>
            <p className="text-sm text-slate-500">Status becomes CLOSED. Capture prices now — they stay in the database, not Excel.</p>
            <div>
              <label className="lbl">Remark</label>
              <textarea rows={2} value={closeForm.remark} onChange={(e) => setCloseForm((f) => ({ ...f, remark: e.target.value }))} placeholder="Why is this closed?" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              {["unit_price", "price", "total_price", "final_price"].map((key) => (
                <div key={key}>
                  <label className="lbl">{key.replace("_", " ")}</label>
                  <input value={closeForm[key]} onChange={(e) => setCloseForm((f) => ({ ...f, [key]: e.target.value }))} />
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-2">
              <button className="btn-outline" type="button" onClick={() => setCloseOpen(false)}>
                Cancel
              </button>
              <button className="btn-primary" type="button" disabled={busy} onClick={closeOrder}>
                {busy ? "Closing…" : "Close order"}
              </button>
            </div>
          </div>
        </div>
      )}

      {canSave && (
        <div className="sticky-save flex items-center justify-between gap-3" data-tour="wo-save">
          <div className="text-sm text-slate-500">
            {busy ? "Saving…" : dirty || isNew ? "Ctrl/⌘+S to save" : "All changes saved."}
          </div>
          <div className="flex gap-2">
            {!isNew && dirty && (
              <button className="btn-outline" type="button" disabled={busy} onClick={() => setForm(original)}>
                Discard
              </button>
            )}
            <button className="btn-primary" onClick={() => save(false)} disabled={busy || (!isNew && !dirty)}>
              {busy ? "Saving…" : isNew ? "Create request" : "Save"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}


function emptyLine() {
  return { supplier: "", material: "", qty: "", unit: "", notes: "", needed_date: "", unit_price: "" };
}

function LineItemsCard({ form, setForm, options, readOnly, supplierLocked }) {
  const lines = Array.isArray(form.lines) && form.lines.length ? form.lines : [emptyLine()];
  const suppliers = options.supplier || [];
  const itemMap = options.supplier_items || {};
  const locked = readOnly || supplierLocked;

  function setLine(index, patch) {
    setForm((f) => {
      const next = Array.isArray(f.lines) && f.lines.length ? [...f.lines] : [emptyLine()];
      while (next.length <= index) next.push(emptyLine());
      next[index] = { ...emptyLine(), ...next[index], ...patch };
      const extra = {};
      if (index === 0 && Object.prototype.hasOwnProperty.call(patch, "supplier")) {
        extra.supplier = patch.supplier;
      }
      return { ...f, lines: next, ...extra };
    });
  }

  function addLine() {
    setForm((f) => ({
      ...f,
      lines: [...(Array.isArray(f.lines) && f.lines.length ? f.lines : [emptyLine()]), emptyLine()],
    }));
  }

  function removeLine(index) {
    setForm((f) => {
      const current = Array.isArray(f.lines) ? f.lines : [];
      const next = current.filter((_, i) => i !== index);
      const extra = {};
      if (index === 0) extra.supplier = next[0]?.supplier || "";
      return { ...f, lines: next.length ? next : [emptyLine()], ...extra };
    });
  }

  return (
    <div className="card p-5 space-y-3" data-tour="wo-lines">
      <div>
        <div className="font-semibold">Items & suppliers</div>
        <p className="text-xs text-slate-500">
          Type to complete supplier and item names. Alt+Enter adds a row. Add new vendors on Materials.
          Excel still keeps one supplier cell (item 1) and one material summary.
        </p>
      </div>
      {lines.map((line, index) => (
        <div key={index} className="rounded-xl border border-slate-200 dark:border-white/10 p-3 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">Item {index + 1}</div>
            {!readOnly && lines.length > 1 && (
              <button type="button" className="btn-ghost !px-2 !py-1 text-xs" onClick={() => removeLine(index)}>
                Remove
              </button>
            )}
          </div>
          <div className="grid md:grid-cols-12 gap-2">
            <div className="md:col-span-4">
              <label className="lbl">Supplier</label>
              <TypeAhead
                value={line.supplier || ""}
                disabled={locked}
                options={line.supplier && !suppliers.includes(line.supplier) ? [line.supplier, ...suppliers] : suppliers}
                allowCustom={false}
                placeholder="Type to complete a supplier"
                onChange={(v) => setLine(index, { supplier: v })}
              />
            </div>
            <div className="md:col-span-4">
              <label className="lbl">Item they can provide</label>
              <TypeAhead
                value={line.material || ""}
                disabled={readOnly}
                options={itemMap[line.supplier] || []}
                allowCustom
                placeholder={`Item ${index + 1}`}
                onChange={(v) => setLine(index, { material: v })}
              />
            </div>
            <div className="md:col-span-2">
              <label className="lbl">Date</label>
              <input
                type="date"
                value={(line.needed_date || "").slice(0, 10)}
                disabled={readOnly}
                onChange={(e) => setLine(index, { needed_date: e.target.value })}
              />
            </div>
            <div className="md:col-span-1">
              <label className="lbl">Qty</label>
              <input value={line.qty || ""} disabled={readOnly} onChange={(e) => setLine(index, { qty: e.target.value })} />
            </div>
            <div className="md:col-span-1">
              <label className="lbl">Unit</label>
              <input value={line.unit || ""} disabled={readOnly} onChange={(e) => setLine(index, { unit: e.target.value })} placeholder="pcs" />
            </div>
          </div>
        </div>
      ))}
      {!readOnly && (
        <button type="button" className="btn-outline" onClick={addLine}>
          + Add item
        </button>
      )}
    </div>
  );
}
