import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { FileText, PenLine, Send, Stamp } from "lucide-react";
import { api } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";
import { useLiveReload } from "../lib/live.js";
import { useTour } from "../context/TourContext.jsx";
import SignaturePad from "../components/SignaturePad.jsx";
import SignSuccess from "../components/SignSuccess.jsx";

const LANES = [
  { id: "incoming", label: "New slips", hint: "Assign a technician" },
  { id: "assigned", label: "With technician", hint: "Update suppliers, then send to manager(s)" },
  { id: "changes", label: "Changes requested", hint: "Fix what the manager wrote, send again" },
  { id: "to_sign", label: "Waiting for signature", hint: "Selected managers review the PDF" },
  { id: "ready", label: "Signed · send on", hint: "Holder sends to Accounts or someone else" },
  { id: "accounts", label: "Sent to Accounts", hint: "Done" },
];

const STATE_LABEL = {
  none: "New",
  assigned: "Assigned",
  changes_requested: "Changes requested",
  submitted: "Waiting for signature",
  approved: "Signed · locked",
  sent_to_accounts: "In Accounts",
};

export default function PoApprovals() {
  const { user } = useAuth();
  const { toast, ask } = useUi();
  const { startSigning, active: tourActive } = useTour();
  const tick = useLiveReload();
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState(null);
  const [q, setQ] = useState("");
  const [lane, setLane] = useState("");
  const [selected, setSelected] = useState(params.get("id") || "");
  const [detail, setDetail] = useState(null);
  const [pdfUrl, setPdfUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [assignee, setAssignee] = useState("");
  const [comment, setComment] = useState("");
  const [signature, setSignature] = useState("");
  const [pickedManagers, setPickedManagers] = useState([]);
  const [returnTo, setReturnTo] = useState("");
  const [routeTo, setRouteTo] = useState("");
  const [accountsTo, setAccountsTo] = useState("");
  const [celebrate, setCelebrate] = useState(false);

  function loadInbox() {
    api
      .get(`/api/po-approvals${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`)
      .then((d) => {
        setData(d);
        setLane((prev) => prev || d.default_lane || "incoming");
      })
      .catch((e) => setError(e.message));
  }

  useEffect(() => {
    const timer = window.setTimeout(loadInbox, q ? 220 : 0);
    return () => window.clearTimeout(timer);
  }, [q, tick]);

  useEffect(() => {
    const id = params.get("id");
    if (id) setSelected(id);
  }, [params]);

  useEffect(() => {
    if (!data || !selected) return;
    for (const l of LANES) {
      if ((data.lanes?.[l.id] || []).some((row) => row.record_id === selected)) {
        setLane(l.id);
        return;
      }
    }
  }, [selected, data]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return undefined;
    }
    let cancelled = false;
    api
      .get(`/api/work-orders/${encodeURIComponent(selected)}/approval`)
      .then((d) => {
        if (cancelled) return;
        setDetail(d);
        setAssignee(d.approval?.assignee || d.caps?.technicians?.[0]?.label || "");
        setComment(d.approval?.state === "changes_requested" ? "" : d.approval?.comment || "");
        setSignature("");
        setError("");
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [selected, tick]);

  useEffect(() => {
    if (!selected) {
      setPdfUrl("");
      return undefined;
    }
    let url = "";
    api
      .blob(`/api/work-orders/${encodeURIComponent(selected)}/approval/pdf`)
      .then((blob) => {
        url = URL.createObjectURL(blob);
        setPdfUrl(url);
      })
      .catch(() => setPdfUrl(""));
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [selected, detail?.approval?.state, detail?.approval?.updated_at]);

  const rows = useMemo(() => data?.lanes?.[lane] || [], [data, lane]);

  function openItem(id, itemLane) {
    setSelected(id);
    if (itemLane) setLane(itemLane);
    setParams({ id }, { replace: true });
  }

  async function run(path, body, { confirm, confirmLabel } = {}) {
    if (confirm) {
      const ok = await ask({ title: confirm, confirmLabel: confirmLabel || "Continue" });
      if (!ok) return;
    }
    setBusy(true);
    setError("");
    try {
      const d = await api.post(`/api/work-orders/${encodeURIComponent(selected)}${path}`, body || {});
      setDetail((prev) => ({ ...prev, approval: d.approval, caps: d.caps }));
      toast(d.approval?.state === "approved" ? "PO signed and locked" : "PO updated", "success");
      if (path.includes("decide") && body?.approve) {
        setSignature("");
        setCelebrate(true);
      }
      loadInbox();
    } catch (e) {
      setError(typeof e.detail === "string" ? e.detail : e.message);
    } finally {
      setBusy(false);
    }
  }

  const a = detail?.approval || {};
  const caps = detail?.caps || {};
  const item = detail?.item || {};
  const techs = caps.technicians || data?.technicians || [];
  const who = user?.full_name || user?.username || "";

  return (
    <div className="space-y-5">
      <div className="page-head" data-tour="appr-head">
        <div>
          <div className="page-kicker">Digital signature</div>
          <h1 className="text-2xl font-bold tracking-tight">Purchase Approval</h1>
          <p className="text-sm text-slate-500">
            Assign a technician, then send the purchase slip to one, two, or three managers. A manager draws a digital
            signature (it prints on the PDF at corporate size) and sends the signed slip back to the sender or someone
            else. That person can send it to Accounts or another person. Unassign if it was given to the wrong technician.
          </p>
        </div>
        {!tourActive && (
          <button
            type="button"
            className="btn-outline shrink-0 self-start"
            title="Walk me through signing a purchase slip"
            onClick={startSigning}
          >
            <PenLine size={14} /> How signing works
          </button>
        )}
      </div>

      <ol className="grid sm:grid-cols-5 gap-2 text-xs" data-tour="appr-steps">
        {[
          ["1. Receive", "PO number lands here"],
          ["2. Assign", "Dispatcher picks a technician"],
          ["3. Work", "Tech updates suppliers / items"],
          ["4. Sign", "Manager signs the PDF — or returns it"],
          ["5. Accounts", "Dispatcher sends the locked PO"],
        ].map(([t, h]) => (
          <li key={t} className="card px-3 py-2">
            <div className="font-semibold">{t}</div>
            <div className="text-slate-500">{h}</div>
          </li>
        ))}
      </ol>

      <div className="flex flex-wrap gap-2" data-tour="appr-lanes">
        {LANES.map((l) => {
          const n = data?.counts?.[l.id] || 0;
          return (
            <button
              key={l.id}
              type="button"
              className={`tab-btn ${lane === l.id ? "is-on" : ""}`}
              onClick={() => setLane(l.id)}
            >
              {l.label}
              <span className="ml-1 text-slate-400">{n}</span>
            </button>
          );
        })}
      </div>
      <p className="text-xs text-slate-500">{LANES.find((l) => l.id === lane)?.hint}</p>

      <div className="grid lg:grid-cols-[minmax(280px,380px)_1fr] gap-4 items-start">
        <div className="space-y-3" data-tour="appr-list">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search WO, PO, supplier, technician…"
            aria-label="Search POs"
          />
          <div className="card overflow-hidden max-h-[70vh] overflow-y-auto">
            {rows.map((row) => (
              <button
                key={row.record_id}
                type="button"
                className={`w-full text-left px-4 py-3 border-b border-slate-100 dark:border-white/5 ${
                  selected === row.record_id ? "bg-sky-50/80 dark:bg-sky-500/10" : "hover:bg-slate-50 dark:hover:bg-white/5"
                }`}
                onClick={() => openItem(row.record_id, row.lane)}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="font-semibold truncate">{row.work_order_id || row.record_id}</div>
                  <span className="text-[10px] uppercase tracking-wider text-slate-400 shrink-0">
                    {STATE_LABEL[row.approval?.state] || row.approval?.state}
                  </span>
                </div>
                <div className="text-sm text-slate-600 dark:text-slate-300 truncate">
                  {row.po_number ? `PO ${row.po_number}` : "No PO #"} · {row.supplier || "No supplier"}
                </div>
                <div className="text-xs text-slate-500 truncate">
                  {row.approval?.assignee || row.assigned_to || "Unassigned"} · {row.department || "—"}
                </div>
              </button>
            ))}
            {!rows.length && (
              <div className="px-4 py-10 text-sm text-slate-500 text-center">
                {data ? "Nothing in this step." : "Loading POs…"}
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4 min-w-0">
          {!selected || !detail ? (
            <div className="card p-8 text-sm text-slate-500">Pick a PO on the left. Hello {who}.</div>
          ) : (
            <>
              <div className="card p-5 space-y-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-xs uppercase tracking-wider text-slate-400">IM WO {item.work_order_id}</div>
                    <div className="text-lg font-semibold">PO {item.po_number || "—"}</div>
                    <div className="text-sm text-slate-500">
                      {item.supplier || "No supplier"} · {item.department || "—"} · {item.status || "—"}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Link className="btn-outline" to={`/work-orders/${encodeURIComponent(selected)}`}>
                      Open material request
                    </Link>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 text-sm">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 dark:bg-white/10">
                    {STATE_LABEL[a.state] || a.state}
                  </span>
                  {a.assignee ? <span className="text-slate-500">Technician {a.assignee}</span> : null}
                  {a.holder ? <span className="text-slate-500">Holding: {a.holder}</span> : null}
                  {(a.manager_list || []).length ? (
                    <span className="text-slate-500">Managers {(a.manager_list || []).join(", ")}</span>
                  ) : null}
                  {a.locked ? <span className="text-emerald-700 font-medium">Locked — cannot be changed</span> : null}
                </div>
                {a.comment && a.state === "changes_requested" ? (
                  <div className="rounded-lg bg-amber-50 dark:bg-amber-500/10 px-3 py-2 text-sm text-amber-900 dark:text-amber-100">
                    Manager asked for: {a.comment}
                  </div>
                ) : null}
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
                    <button
                      className="btn-primary"
                      disabled={busy || !assignee}
                      onClick={() => run("/approval/assign", { assignee })}
                    >
                      <Send size={14} /> Assign
                    </button>
                    {caps.can_unassign && (
                      <button className="btn-outline" disabled={busy} onClick={() => run("/approval/unassign")}>
                        Unassign
                      </button>
                    )}
                  </div>
                )}
                {!caps.can_assign && caps.can_unassign && (
                  <button className="btn-outline" disabled={busy} onClick={() => run("/approval/unassign")}>
                    Unassign
                  </button>
                )}

                {caps.can_submit && (
                  <div className="space-y-2">
                    <p className="text-sm text-slate-500">
                      Update suppliers and items on the material request, then send this PDF to one, two, or three
                      managers.
                    </p>
                    <div>
                      <label className="lbl">Managers (pick 1–3)</label>
                      <div className="flex flex-col gap-1">
                        {(caps.managers || []).map((m) => {
                          const on = pickedManagers.includes(m.username);
                          return (
                            <label key={m.username} className="flex items-center gap-2 text-sm">
                              <input
                                type="checkbox"
                                className="!w-auto"
                                checked={on}
                                onChange={() => {
                                  setPickedManagers((prev) => {
                                    if (on) return prev.filter((x) => x !== m.username);
                                    if (prev.length >= 3) return prev;
                                    return [...prev, m.username];
                                  });
                                }}
                              />
                              {m.label}
                            </label>
                          );
                        })}
                        {!(caps.managers || []).length && (
                          <p className="text-xs text-slate-500">No managers with sign permission yet.</p>
                        )}
                      </div>
                    </div>
                    <button
                      className="btn-primary"
                      disabled={busy || !pickedManagers.length}
                      onClick={() => run("/approval/submit", { managers: pickedManagers })}
                    >
                      <FileText size={14} /> Send to {pickedManagers.length || "—"} manager{pickedManagers.length === 1 ? "" : "s"}
                    </button>
                  </div>
                )}

                {caps.can_decide && (
                  <div className="space-y-3">
                    <p className="text-sm text-slate-500">
                      Review the PDF. Draw a signature to approve (this locks prices and suppliers), then send the signed
                      slip back to the sender or someone else. Or write the changes and return it unsigned.
                    </p>
                    <div>
                      <label className="lbl">Digital signature</label>
                      <SignaturePad value={signature} onChange={setSignature} />
                    </div>
                    <div>
                      <label className="lbl">Send signed slip to</label>
                      <select
                        value={returnTo}
                        onChange={(e) => setReturnTo(e.target.value)}
                        data-tour="sign-return-to"
                      >
                        <option value={a.assignee || ""}>{a.assignee ? `Sender · ${a.assignee}` : "Sender"}</option>
                        {(caps.people || []).map((p) => (
                          <option key={p.username} value={p.username}>
                            {p.label} ({p.role})
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="lbl">Changes (required to return unsigned)</label>
                      <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        className="btn-primary"
                        disabled={busy || !signature}
                        data-tour="sign-send"
                        onClick={() =>
                          run(
                            "/approval/decide",
                            { approve: true, signature_png: signature, comment, return_to: returnTo },
                            {
                              confirm: "Sign and lock this purchase slip? After this, suppliers, items and prices cannot be changed.",
                              confirmLabel: "Sign & send",
                            }
                          )
                        }
                      >
                        <Stamp size={14} /> Sign &amp; send
                      </button>
                      <button
                        className="btn-outline"
                        disabled={busy || !comment.trim()}
                        data-tour="sign-return"
                        onClick={() => run("/approval/decide", { approve: false, comment })}
                      >
                        Return with changes
                      </button>
                    </div>
                  </div>
                )}

                {caps.can_route && (
                  <div className="flex flex-wrap gap-2 items-end">
                    <div className="flex-1 min-w-[12rem]">
                      <label className="lbl">Send signed slip to someone else</label>
                      <select value={routeTo} onChange={(e) => setRouteTo(e.target.value)}>
                        <option value="">—</option>
                        {(caps.people || []).map((p) => (
                          <option key={p.username} value={p.username}>
                            {p.label} ({p.role})
                          </option>
                        ))}
                      </select>
                    </div>
                    <button
                      className="btn-outline"
                      disabled={busy || !routeTo}
                      onClick={() => run("/approval/route", { to: routeTo })}
                    >
                      Send
                    </button>
                  </div>
                )}

                {caps.can_send_accounts && (
                  <div className="flex flex-wrap gap-2 items-end" data-tour="appr-accounts">
                    <div className="flex-1 min-w-[12rem]">
                      <label className="lbl">Accounts (optional person)</label>
                      <select value={accountsTo} onChange={(e) => setAccountsTo(e.target.value)}>
                        <option value="">Accounts inbox</option>
                        {(caps.people || []).map((p) => (
                          <option key={p.username} value={p.username}>
                            {p.label} ({p.role})
                          </option>
                        ))}
                      </select>
                    </div>
                    <button
                      className="btn-primary"
                      disabled={busy}
                      onClick={() =>
                        run(
                          "/approval/send-accounts",
                          { to: accountsTo },
                          { confirm: "Send this signed purchase slip to Accounts?", confirmLabel: "Send" }
                        )
                      }
                    >
                      <PenLine size={14} /> Send to Accounts
                    </button>
                  </div>
                )}
              </div>

              <div className="card overflow-hidden min-h-[28rem]" data-tour="appr-pdf">
                <div className="px-4 py-2 text-xs font-medium text-slate-500 border-b border-slate-100 dark:border-white/5 flex justify-between">
                  <span>PDF for signature</span>
                  <button
                    type="button"
                    className="text-brand-700 dark:text-cyan-300"
                    onClick={() =>
                      api.download(`/api/work-orders/${encodeURIComponent(selected)}/approval/pdf`, `PO_${item.work_order_id || selected}.pdf`)
                    }
                  >
                    Download
                  </button>
                </div>
                {pdfUrl ? (
                  <iframe title="PO PDF" src={pdfUrl} className="w-full h-[32rem] bg-slate-100" />
                ) : (
                  <div className="p-8 text-sm text-slate-500">Preparing PDF…</div>
                )}
              </div>

              {(a.events || []).length > 0 && (
                <div className="card p-4">
                  <div className="font-semibold text-sm mb-2">History</div>
                  <ul className="text-xs text-slate-500 space-y-1">
                    {a.events.map((ev) => (
                      <li key={ev.id}>
                        {ev.created_at} · {ev.username} · {ev.action}
                        {ev.comment ? ` — ${ev.comment}` : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      </div>
      {celebrate && (
        <SignSuccess
          note={`PO ${item.po_number || item.work_order_id || ""} · sent to ${returnTo || a.assignee || "the sender"}`}
          onDone={() => setCelebrate(false)}
        />
      )}
    </div>
  );
}
