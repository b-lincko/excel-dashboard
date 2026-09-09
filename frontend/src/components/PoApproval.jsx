import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BellRing, FileText, Send, Stamp } from "lucide-react";
import { api } from "../lib/api.js";
import { useTour } from "../context/TourContext.jsx";
import { useUi } from "../context/UiContext.jsx";
import SignSuccess from "./SignSuccess.jsx";
import SignWindow from "./SignWindow.jsx";

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
  const { ask, toast } = useUi();
  const [data, setData] = useState(null);
  const [assignee, setAssignee] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [celebrate, setCelebrate] = useState(false);
  const [celebrateNote, setCelebrateNote] = useState("");
  const [signOpen, setSignOpen] = useState(false);
  const [pdfUrl, setPdfUrl] = useState("");

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

  useEffect(() => {
    if (!woId) {
      setPdfUrl("");
      return undefined;
    }
    let url = "";
    api
      .blob(`/api/work-orders/${encodeURIComponent(woId)}/approval/pdf`)
      .then((blob) => {
        url = URL.createObjectURL(blob);
        setPdfUrl(url);
      })
      .catch(() => setPdfUrl(""));
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [woId, data?.approval?.state, data?.approval?.updated_at]);

  async function run(path, body, { confirm, confirmLabel } = {}) {
    if (confirm) {
      const ok = await ask({ title: confirm, confirmLabel: confirmLabel || "Continue" });
      if (!ok) return false;
    }
    setBusy(true);
    setError("");
    try {
      const d = await api.post(`/api/work-orders/${encodeURIComponent(woId)}${path}`, body || {});
      setData((prev) => ({ ...prev, approval: d.approval, caps: d.caps }));
      onNotice?.(d.approval?.state === "approved" ? "PO signed and locked" : "PO updated");
      if (path.includes("ping")) toast("Follow-up sent", "success");
      return true;
    } catch (e) {
      setError(typeof e.detail === "string" ? e.detail : e.message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function decideInWindow(body) {
    const ok = await run(
      "/approval/decide",
      body,
      body.approve
        ? {
            confirm: "Sign and lock this purchase slip? After this, suppliers, items and prices cannot be changed.",
            confirmLabel: "Sign & send",
          }
        : {}
    );
    if (ok) {
      if (body.approve) {
        setCelebrateNote(body.return_to ? `sent to ${body.return_to}` : "");
        setCelebrate(true);
      }
      setSignOpen(false);
    }
  }

  if (!data) return <div className="text-sm text-slate-500">{error || "Loading approval…"}</div>;
  const a = data.approval || {};
  const caps = data.caps || {};
  const techs = caps.technicians || [];
  const item = data.item || {};

  return (
    <div className="card p-5 space-y-4">
      <div>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="font-semibold">PO approval</div>
            <p className="text-xs text-slate-500">
              Assign a technician, they send the slip to one to three managers, a manager signs (the slip locks), then it
              goes to Accounts. The signatures desk has the full step-by-step view.
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
        {a.holder ? <span className="text-slate-500">Holding: {a.holder}</span> : null}
        {a.locked ? <span className="text-emerald-700">Locked</span> : null}
      </div>
      {a.comment && a.state === "changes_requested" ? (
        <div className="rounded-lg bg-amber-50 dark:bg-amber-500/10 px-3 py-2 text-sm text-amber-900 dark:text-amber-100">
          Manager asked for: {a.comment}
        </div>
      ) : null}
      {error && <div className="text-sm text-rose-600">{error}</div>}

      {caps.can_assign && (
        <div className="flex flex-wrap gap-2 items-center">
          <select value={assignee} onChange={(e) => setAssignee(e.target.value)} className="flex-1 min-w-[12rem]">
            <option value="">Pick a technician…</option>
            {techs.map((t) => (
              <option key={t.username} value={t.label}>
                {t.label}
              </option>
            ))}
          </select>
          <button className="btn-primary" disabled={busy || !assignee} onClick={() => run("/approval/assign", { assignee })}>
            <Send size={14} /> Assign
          </button>
          {caps.can_unassign && (
            <button
              className="btn-ghost text-sm text-slate-500"
              disabled={busy}
              onClick={() =>
                run("/approval/unassign", {}, {
                  confirm: "Unassign this slip? It goes back to “New”.",
                  confirmLabel: "Unassign",
                })
              }
            >
              Unassign
            </button>
          )}
        </div>
      )}
      {!caps.can_assign && caps.can_unassign && (
        <button
          className="btn-ghost text-sm text-slate-500"
          disabled={busy}
          onClick={() =>
            run("/approval/unassign", {}, { confirm: "Unassign this slip? It goes back to “New”.", confirmLabel: "Unassign" })
          }
        >
          Unassign technician
        </button>
      )}

      {caps.can_submit && (
        <div className="space-y-2">
          <p className="text-sm text-slate-500">Send the current PDF to the managers who must sign (up to three).</p>
          <button className="btn-primary" disabled={busy} onClick={() => run("/approval/submit", {})}>
            <FileText size={14} /> Send to managers
          </button>
        </div>
      )}

      {caps.can_decide && (
        <div className="space-y-2">
          <p className="text-sm text-slate-500">
            The slip is waiting for your signature. Review the PDF, then sign to lock it — or return it with changes.
          </p>
          <button type="button" className="btn-primary" onClick={() => setSignOpen(true)}>
            <Stamp size={14} /> Review &amp; sign…
          </button>
        </div>
      )}

      {caps.can_ping && (
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn-outline" disabled={busy} onClick={() => run("/approval/ping", {})}>
            <BellRing size={14} /> Follow up
          </button>
          <span className="text-xs text-slate-500">
            Nudge {caps.ping_label || "them"} — inbox ping, plus an email when mail is on.
          </span>
        </div>
      )}

      {caps.can_route && (
        <p className="text-sm text-slate-500">
          This signed slip is with you — use the signatures desk to forward it or send it to Accounts.
        </p>
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

      <SignWindow
        open={signOpen}
        onClose={() => {
          if (!busy) setSignOpen(false);
        }}
        busy={busy}
        error={signOpen ? error : ""}
        item={item}
        approval={a}
        caps={caps}
        pdfUrl={pdfUrl}
        onDownload={() =>
          api.download(
            `/api/work-orders/${encodeURIComponent(woId)}/approval/pdf`,
            `PO_${item.work_order_id || woId}.pdf`
          )
        }
        onDecide={(body) => decideInWindow(body)}
      />
      {celebrate && <SignSuccess note={celebrateNote} onDone={() => setCelebrate(false)} />}
    </div>
  );
}
