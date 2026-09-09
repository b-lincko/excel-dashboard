import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api.js";
import { useTour } from "../context/TourContext.jsx";
import SignaturePad from "./SignaturePad.jsx";
import SignSuccess from "./SignSuccess.jsx";

const LABELS = {
  none: "Not started",
  assigned: "Assigned to technician",
  submitted: "Waiting for manager signature",
  changes_requested: "Manager requested changes",
  approved: "Approved — PO locked",
  sent_to_accounts: "Sent to Accounts",
};

export default function PoApproval({ woId, onNotice }) {
  const { startSigning } = useTour();
  const [data, setData] = useState(null);
  const [assignee, setAssignee] = useState("");
  const [comment, setComment] = useState("");
  const [signature, setSignature] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [celebrate, setCelebrate] = useState(false);

  function load() {
    api
      .get(`/api/work-orders/${encodeURIComponent(woId)}/approval`)
      .then((d) => {
        setData(d);
        setAssignee(d.approval?.assignee || d.caps?.technicians?.[0]?.label || "");
      })
      .catch((e) => setError(e.message));
  }

  useEffect(() => {
    if (woId) load();
  }, [woId]);

  async function run(path, body) {
    setBusy(true);
    setError("");
    try {
      const d = await api.post(`/api/work-orders/${encodeURIComponent(woId)}${path}`, body || {});
      setData((prev) => ({ ...prev, approval: d.approval, caps: d.caps }));
      onNotice?.(d.approval?.state === "approved" ? "PO signed and locked" : "PO updated");
      if (path.includes("decide") && body?.approve) {
        setSignature("");
        setCelebrate(true);
      }
    } catch (e) {
      setError(typeof e.detail === "string" ? e.detail : e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!data) return <div className="text-sm text-slate-500">{error || "Loading approval…"}</div>;
  const a = data.approval || {};
  const caps = data.caps || {};
  const techs = caps.technicians || [];

  return (
    <div className="card p-5 space-y-4">
      <div>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="font-semibold">PO approval</div>
            <p className="text-xs text-slate-500">
              Abubacar (or anyone granted PO dispatch) assigns a technician. That person updates the PO, sends a PDF to
              the operational manager, who signs or returns written changes. After a signature the PO is locked. Dispatch
              then sends it to Accounts.
            </p>
          </div>
          {woId ? (
            <div className="flex flex-col gap-2 shrink-0">
              <Link className="btn-outline" to={`/approvals?id=${encodeURIComponent(woId)}`}>
                Open signatures desk
              </Link>
              <button type="button" className="btn-ghost !px-2 !py-1 text-xs" onClick={startSigning}>
                How signing works
              </button>
            </div>
          ) : null}
        </div>
      </div>
      <div className="flex flex-wrap gap-2 text-sm">
        <span className="rounded-full bg-slate-100 px-2 py-0.5 dark:bg-white/10">{LABELS[a.state] || a.state || "Not started"}</span>
        {a.assignee ? <span className="text-slate-500">Technician {a.assignee}</span> : null}
        {a.locked ? <span className="text-emerald-700">Locked</span> : null}
      </div>
      {a.comment ? <p className="text-sm text-amber-800 dark:text-amber-200">Manager: {a.comment}</p> : null}
      {error && <div className="text-sm text-rose-600">{error}</div>}

      {caps.can_assign && (
        <div className="flex flex-wrap gap-2 items-end">
          <div className="flex-1 min-w-[12rem]">
            <label className="lbl">Assign technician</label>
            <select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
              <option value="">—</option>
              {techs.map((t) => (
                <option key={t.username} value={t.label}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
          <button className="btn-primary" disabled={busy || !assignee} onClick={() => run("/approval/assign", { assignee })}>
            Assign PO
          </button>
        </div>
      )}

      {caps.can_submit && (
        <div className="space-y-2">
          <p className="text-sm text-slate-500">Send the current PO as a PDF to the operational manager.</p>
          <div className="flex gap-2">
            <button className="btn-primary" disabled={busy} onClick={() => run("/approval/submit")}>
              Send to manager
            </button>
            <button
              className="btn-outline"
              type="button"
              onClick={() => api.download(`/api/work-orders/${encodeURIComponent(woId)}/approval/pdf`, `PO_${woId}.pdf`)}
            >
              Preview PDF
            </button>
          </div>
        </div>
      )}

      {caps.can_decide && (
        <div className="space-y-3">
          <p className="text-sm text-slate-500">Review the PDF, then sign to approve or write the changes and return it.</p>
          <button
            className="btn-outline"
            type="button"
            onClick={() => api.download(`/api/work-orders/${encodeURIComponent(woId)}/approval/pdf`, `PO_${woId}.pdf`)}
          >
            Open PDF
          </button>
          <div>
            <label className="lbl">Digital signature</label>
            <SignaturePad value={signature} onChange={setSignature} />
          </div>
          <div>
            <label className="lbl">Changes (required to return)</label>
            <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
          <div className="flex gap-2">
            <button className="btn-primary" disabled={busy || !signature} onClick={() => run("/approval/decide", { approve: true, signature_png: signature, comment })}>
              Sign &amp; approve
            </button>
            <button className="btn-outline" disabled={busy || !comment.trim()} onClick={() => run("/approval/decide", { approve: false, comment })}>
              Return with changes
            </button>
          </div>
        </div>
      )}

      {caps.can_send_accounts && (
        <button className="btn-primary" disabled={busy} onClick={() => run("/approval/send-accounts")}>
          Send to Accounts
        </button>
      )}

      {(a.events || []).length > 0 && (
        <ul className="text-xs text-slate-500 space-y-1">
          {a.events.map((ev) => (
            <li key={ev.id}>
              {ev.created_at} · {ev.username} · {ev.action}
              {ev.comment ? ` — ${ev.comment}` : ""}
            </li>
          ))}
        </ul>
      )}
      {celebrate && <SignSuccess onDone={() => setCelebrate(false)} />}
    </div>
  );
}
