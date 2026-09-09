import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { BellRing, ChevronDown, ChevronUp, FileText, PenLine, Send, Stamp } from "lucide-react";
import { api } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";
import { useLiveReload } from "../lib/live.js";
import { useTour } from "../context/TourContext.jsx";
import SignSuccess from "../components/SignSuccess.jsx";
import SignWindow from "../components/SignWindow.jsx";

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

const STAGES = ["Request", "Technician", "Managers", "Signed", "Accounts"];
const STAGE_OF_STATE = {
  none: 0,
  assigned: 1,
  changes_requested: 1,
  submitted: 2,
  approved: 3,
  sent_to_accounts: 4,
};

function statusStory(a) {
  const state = a.state || "none";
  if (state === "none") {
    return {
      title: "New slip — nothing started yet",
      next: "Assign a technician. They update suppliers and items, then send the slip to one, two, or three managers.",
    };
  }
  if (state === "assigned") {
    return {
      title: `With ${a.assignee || "the technician"}`,
      next: "They update suppliers and items, then send it to the managers. Use Follow up to nudge them if it waits.",
    };
  }
  if (state === "changes_requested") {
    return {
      title: `Changes requested from ${a.assignee || "the technician"}`,
      next: a.comment
        ? `The manager asked: “${a.comment}”. They fix the slip and send it to the managers again.`
        : "The technician fixes the slip and sends it to the managers again.",
    };
  }
  if (state === "submitted") {
    const managers = (a.manager_list || []).join(", ");
    return {
      title: `Waiting for signature — ${managers || "managers"}`,
      next: "A manager opens Review & sign, reads the PDF, then signs (this locks the slip) or returns it with written changes.",
    };
  }
  if (state === "approved") {
    return {
      title: `Signed by ${a.signed_by || "a manager"} — locked`,
      next: `${a.holder ? `${a.holder} holds the signed slip` : "The signed slip is ready"} and can forward it or send it to Accounts.`,
    };
  }
  return {
    title: `Filed with Accounts${a.accounts_by ? ` by ${a.accounts_by}` : ""}`,
    next: "Done. The signed slip stays searchable in History.",
  };
}

export default function PoApprovals() {
  const { user } = useAuth();
  const { toast, ask } = useUi();
  const { startSigning, active: tourActive, step: tourStep } = useTour();
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
  const [pickedManagers, setPickedManagers] = useState([]);
  const [celebrateNote, setCelebrateNote] = useState("");
  const [routeTo, setRouteTo] = useState("");
  const [accountsTo, setAccountsTo] = useState("");
  const [pingNote, setPingNote] = useState("");
  const [celebrate, setCelebrate] = useState(false);
  const [signOpen, setSignOpen] = useState(false);
  const [signStep, setSignStep] = useState(1);
  const [pdfOpen, setPdfOpen] = useState(true);
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
        setPickedManagers([]);
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

  // When the signing tour reaches the hands-on steps, open the sign window so
  // the tour points at the real controls.
  useEffect(() => {
    if (!tourActive || !tourStep) return;
    if (["sign-draw", "sign-choose", "sign-approve", "sign-return"].includes(tourStep.id)) {
      if (detail?.caps?.can_decide) {
        setSignStep(2);
        setSignOpen(true);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tourActive, tourStep?.id]);

  const rows = useMemo(() => data?.lanes?.[lane] || [], [data, lane]);

  function openItem(id, itemLane) {
    setSelected(id);
    if (itemLane) setLane(itemLane);
    setParams({ id }, { replace: true });
  }

  async function run(path, body, { confirm, confirmLabel } = {}) {
    if (confirm) {
      const ok = await ask({ title: confirm, confirmLabel: confirmLabel || "Continue" });
      if (!ok) return false;
    }
    setBusy(true);
    setError("");
    try {
      const d = await api.post(`/api/work-orders/${encodeURIComponent(selected)}${path}`, body || {});
      setDetail((prev) => ({ ...prev, approval: d.approval, caps: d.caps }));
      toast(d.approval?.state === "approved" ? "PO signed and locked" : "PO updated", "success");
      if (path.includes("ping")) setPingNote("");
      loadInbox();
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
      setCelebrateNote(
        body.return_to
          ? `sent to ${body.return_to}`
          : body.approve
            ? "sent to the sender"
            : ""
      );
      setSignOpen(false);
    }
  }

  const a = detail?.approval || {};
  const caps = detail?.caps || {};
  const item = detail?.item || {};
  const techs = caps.technicians || data?.technicians || [];
  const who = user?.full_name || user?.username || "";
  const story = statusStory(a);
  const stage = STAGE_OF_STATE[a.state] ?? 0;

  const pingWaitMin = useMemo(() => {
    if (!caps.last_ping_at || !caps.ping_cooldown_minutes) return 0;
    const last = new Date(String(caps.last_ping_at).replace(" ", "T") + "Z").getTime();
    if (Number.isNaN(last)) return 0;
    const end = last + Number(caps.ping_cooldown_minutes) * 60000;
    return Math.max(0, Math.ceil((end - Date.now()) / 60000));
  }, [caps.last_ping_at, caps.ping_cooldown_minutes]);

  function toggleManager(username) {
    setPickedManagers((prev) => {
      if (prev.includes(username)) return prev.filter((x) => x !== username);
      if (prev.length >= 3) return prev;
      return [...prev, username];
    });
  }

  return (
    <div className="space-y-5">
      <div className="page-head" data-tour="appr-head">
        <div>
          <div className="page-kicker">Digital signature</div>
          <h1 className="text-2xl font-bold tracking-tight">Purchase Approval</h1>
          <p className="text-sm text-slate-500 max-w-3xl">
            One slip, five steps: assign a technician, they send it to managers, a manager signs (the slip locks), then
            it goes to Accounts. Follow the steps below — every screen shows only the action that is due next.
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

      {/* Workflow stepper */}
      <div className="card px-4 py-3" data-tour="appr-steps">
        <ol className="flex flex-wrap items-center gap-x-2 gap-y-2 text-xs">
          {STAGES.map((label, i) => {
            const done = i < stage;
            const now = i === stage;
            return (
              <li key={label} className="flex items-center gap-2">
                {i > 0 && <span className="text-slate-300 dark:text-white/20">→</span>}
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-semibold ${
                    now
                      ? "bg-brand-700 text-white"
                      : done
                        ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
                        : "bg-slate-100 text-slate-400 dark:bg-white/5 dark:text-slate-500"
                  }`}
                >
                  {done ? "✓" : i + 1} {label}
                </span>
              </li>
            );
          })}
        </ol>
        {detail && (
          <div className="mt-2.5 text-sm">
            <span className="font-semibold">{story.title}.</span>{" "}
            <span className="text-slate-500">{story.next}</span>
          </div>
        )}
      </div>

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
              {/* The request */}
              <div className="card p-5 space-y-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-xs uppercase tracking-wider text-slate-400">IM WO {item.work_order_id}</div>
                    <div className="text-lg font-semibold">PO {item.po_number || "—"}</div>
                    <div className="text-sm text-slate-500">
                      {item.supplier || "No supplier"} · {item.department || "—"} · {item.status || "—"}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {caps.can_decide && (
                      <button
                        type="button"
                        className="btn-primary"
                        onClick={() => {
                          setSignStep(1);
                          setSignOpen(true);
                        }}
                      >
                        <Stamp size={14} /> Review &amp; sign…
                      </button>
                    )}
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
                {error && (
                  <div className="rounded-lg bg-rose-50 dark:bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
                    {error}
                  </div>
                )}
              </div>

              {/* Next actions */}
              <div className="card p-5 space-y-4">
                <div className="text-sm font-semibold">Next step</div>

                {caps.can_assign && (
                  <div className="rounded-xl border border-slate-200 dark:border-white/10 p-3 space-y-2">
                    <div className="text-sm font-medium">1 · Assign a technician</div>
                    <p className="text-xs text-slate-500">
                      The technician updates suppliers and items on the material request, then sends the slip to the
                      managers. You can unassign if it was given to the wrong person.
                    </p>
                    <div className="flex flex-wrap gap-2 items-center">
                      <select value={assignee} onChange={(e) => setAssignee(e.target.value)} className="flex-1 min-w-[12rem]">
                        <option value="">Pick a technician…</option>
                        {techs.map((t) => (
                          <option key={t.username} value={t.label}>
                            {t.label}
                          </option>
                        ))}
                      </select>
                      <button
                        className="btn-primary"
                        disabled={busy || !assignee}
                        onClick={() => run("/approval/assign", { assignee })}
                      >
                        <Send size={14} /> Assign
                      </button>
                      {caps.can_unassign && (
                        <button
                          className="btn-ghost text-sm text-slate-500"
                          disabled={busy}
                          onClick={() =>
                            run("/approval/unassign", {}, {
                              confirm: "Unassign this slip? It goes back to “New” and the technician can no longer send it.",
                              confirmLabel: "Unassign",
                            })
                          }
                        >
                          Unassign
                        </button>
                      )}
                    </div>
                  </div>
                )}
                {!caps.can_assign && caps.can_unassign && (
                  <div className="flex justify-end">
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
                      Unassign technician
                    </button>
                  </div>
                )}

                {caps.can_submit && (
                  <div className="rounded-xl border border-slate-200 dark:border-white/10 p-3 space-y-2">
                    <div className="text-sm font-medium">
                      {caps.can_assign ? "2 · " : ""}Send the slip to the manager(s) who must sign
                    </div>
                    <p className="text-xs text-slate-500">
                      Pick one, two, or three managers. They get an inbox ping (and an email when mail is on). The
                      material request should already show the right suppliers and items.
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {(caps.managers || []).map((m) => {
                        const on = pickedManagers.includes(m.username);
                        return (
                          <button
                            key={m.username}
                            type="button"
                            onClick={() => toggleManager(m.username)}
                            className={`px-3 py-1.5 rounded-full border text-sm transition-colors ${
                              on
                                ? "bg-brand-700 text-white border-brand-700"
                                : "border-slate-300 dark:border-white/15 hover:bg-slate-50 dark:hover:bg-white/5"
                            }`}
                          >
                            {m.label}
                          </button>
                        );
                      })}
                      {!(caps.managers || []).length && (
                        <p className="text-xs text-slate-500">
                          No managers with sign permission yet — ask an admin to grant po_approve.
                        </p>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        className="btn-primary"
                        disabled={busy || !pickedManagers.length}
                        onClick={() => run("/approval/submit", { managers: pickedManagers })}
                      >
                        <FileText size={14} /> Send to {pickedManagers.length || "—"} manager
                        {pickedManagers.length === 1 ? "" : "s"}
                      </button>
                      <span className="text-xs text-slate-500">{pickedManagers.length}/3 selected</span>
                    </div>
                  </div>
                )}

                {caps.can_decide && (
                  <div className="rounded-xl border border-slate-200 dark:border-white/10 p-3 space-y-2">
                    <div className="text-sm font-medium">Your signature is needed</div>
                    <p className="text-xs text-slate-500">
                      Open the window, read the PDF, then sign to approve (this locks the slip) or return it with
                      written changes. Nothing is locked until you sign.
                    </p>
                    <button
                      type="button"
                      className="btn-primary"
                      onClick={() => {
                        setSignStep(1);
                        setSignOpen(true);
                      }}
                    >
                      <Stamp size={14} /> Review &amp; sign…
                    </button>
                  </div>
                )}

                {caps.can_route && (
                  <div className="rounded-xl border border-slate-200 dark:border-white/10 p-3 space-y-2">
                    <div className="text-sm font-medium">Pass the signed slip to someone else</div>
                    <p className="text-xs text-slate-500">
                      The slip stays signed and locked — you are only changing who holds it.
                    </p>
                    <div className="flex flex-wrap gap-2 items-center">
                      <select value={routeTo} onChange={(e) => setRouteTo(e.target.value)} className="flex-1 min-w-[12rem]">
                        <option value="">Pick a person…</option>
                        {(caps.people || []).map((p) => (
                          <option key={p.username} value={p.username}>
                            {p.label} ({p.role})
                          </option>
                        ))}
                      </select>
                      <button
                        className="btn-outline"
                        disabled={busy || !routeTo}
                        onClick={() => run("/approval/route", { to: routeTo })}
                      >
                        <Send size={14} /> Send
                      </button>
                    </div>
                  </div>
                )}

                {caps.can_send_accounts && (
                  <div className="rounded-xl border border-slate-200 dark:border-white/10 p-3 space-y-2" data-tour="appr-accounts">
                    <div className="text-sm font-medium">File it with Accounts</div>
                    <p className="text-xs text-slate-500">
                      Final step. The signed slip moves to the Accounts lane — optionally to a specific person.
                    </p>
                    <div className="flex flex-wrap gap-2 items-center">
                      <select value={accountsTo} onChange={(e) => setAccountsTo(e.target.value)} className="flex-1 min-w-[12rem]">
                        <option value="">Accounts inbox</option>
                        {(caps.people || []).map((p) => (
                          <option key={p.username} value={p.username}>
                            {p.label} ({p.role})
                          </option>
                        ))}
                      </select>
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
                  </div>
                )}

                {caps.can_ping && (
                  <div className="rounded-xl bg-slate-50 dark:bg-white/5 p-3 space-y-2" data-tour="appr-followup">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="text-sm font-medium flex items-center gap-1.5">
                        <BellRing size={13} /> Follow up
                      </div>
                      <span className="text-xs text-slate-500">
                        {pingWaitMin > 0
                          ? `You can nudge again in ~${pingWaitMin} min`
                          : caps.last_ping_at
                            ? `Last follow-up ${caps.last_ping_at} UTC`
                            : "No follow-up sent yet"}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">
                      Nudge {caps.ping_label || "them"} — an inbox ping, plus an email when mail is on.
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <input
                        className="flex-1 min-w-[12rem]"
                        value={pingNote}
                        maxLength={200}
                        onChange={(e) => setPingNote(e.target.value)}
                        placeholder="Optional note — e.g. “Please sign today, delivery is waiting”"
                      />
                      <button
                        className="btn-outline"
                        disabled={busy || pingWaitMin > 0}
                        onClick={() => run("/approval/ping", { note: pingNote })}
                      >
                        Send follow-up
                      </button>
                    </div>
                  </div>
                )}

                {!caps.can_assign &&
                  !caps.can_submit &&
                  !caps.can_decide &&
                  !caps.can_route &&
                  !caps.can_send_accounts && (
                    <p className="text-sm text-slate-500">
                      Nothing for you to do on this slip right now — {story.next.charAt(0).toLowerCase()}
                      {story.next.slice(1)}
                    </p>
                  )}
              </div>

              {/* The PDF */}
              <div className="card overflow-hidden" data-tour="appr-pdf">
                <button
                  type="button"
                  className="w-full px-4 py-2.5 text-xs font-medium text-slate-500 flex justify-between items-center"
                  onClick={() => setPdfOpen((v) => !v)}
                >
                  <span>The slip as PDF{item.work_order_id ? ` — ${item.work_order_id}` : ""}</span>
                  <span className="flex items-center gap-3">
                    <span
                      className="text-brand-700 dark:text-cyan-300"
                      onClick={(e) => {
                        e.stopPropagation();
                        api.download(
                          `/api/work-orders/${encodeURIComponent(selected)}/approval/pdf`,
                          `PO_${item.work_order_id || selected}.pdf`
                        );
                      }}
                    >
                      Download
                    </span>
                    {pdfOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </span>
                </button>
                {pdfOpen &&
                  (pdfUrl ? (
                    <iframe title="PO PDF" src={pdfUrl} className="w-full h-[32rem] bg-slate-100 border-t border-slate-100 dark:border-white/5" />
                  ) : (
                    <div className="p-8 text-sm text-slate-500 border-t border-slate-100 dark:border-white/5">
                      Preparing PDF…
                    </div>
                  ))}
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
        startStep={signStep}
        onDownload={() =>
          api.download(
            `/api/work-orders/${encodeURIComponent(selected)}/approval/pdf`,
            `PO_${item.work_order_id || selected}.pdf`
          )
        }
        onDecide={(body) => decideInWindow(body)}
      />

      {celebrate && (
        <SignSuccess
          note={[`PO ${item.po_number || item.work_order_id || ""}`, celebrateNote].filter(Boolean).join(" · ")}
          onDone={() => setCelebrate(false)}
        />
      )}
    </div>
  );
}
