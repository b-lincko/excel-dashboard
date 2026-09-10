import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowRight, Download, Stamp, X } from "lucide-react";
import SignaturePad from "./SignaturePad.jsx";

/**
 * The signing window: a calm, two-step dialog.
 *   1 · View the request  — summary + the actual PDF
 *   2 · Sign the request  — draw, choose the recipient, sign & send (locks),
 *                           or return with written changes.
 */
export default function SignWindow({
  open,
  onClose,
  busy,
  error,
  item,
  approval,
  caps,
  pdfUrl,
  onDownload,
  onDecide,
  startStep = 1,
}) {
  const [step, setStep] = useState(startStep);
  const [signature, setSignature] = useState("");
  const [returnTo, setReturnTo] = useState("");
  const [comment, setComment] = useState("");
  const [showReturn, setShowReturn] = useState(false);

  useEffect(() => {
    if (open) {
      setStep(startStep);
      setSignature("");
      setComment("");
      setShowReturn(false);
    }
  }, [open, startStep]);

  useEffect(() => {
    setReturnTo(approval?.assignee || "");
  }, [approval?.assignee, open]);

  useEffect(() => {
    if (!open) return undefined;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    function onKey(e) {
      if (e.key === "Escape" && !busy) onClose?.();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onClose]);

  if (!open) return null;
  const a = approval || {};
  const people = caps?.people || [];
  const rows = [
    ["MR", item?.work_order_id],
    ["PO number", item?.po_number ? `PO ${item.po_number}` : ""],
    ["Supplier", item?.supplier],
    ["Site", item?.department],
    ["Current status", item?.status],
  ].filter(([, v]) => v);

  return createPortal(
    <div
      className="fixed inset-0 z-[110] grid place-items-center p-3 sm:p-6 bg-slate-900/55 backdrop-blur-[2px]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onClose?.();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Review and sign purchase slip"
        className="w-full max-w-3xl max-h-[92vh] overflow-y-auto rounded-2xl bg-white dark:bg-ink-900 border border-slate-200 dark:border-white/10 shadow-2xl"
      >
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-start justify-between gap-3 px-5 py-4 border-b border-slate-100 dark:border-white/10 bg-white/95 dark:bg-ink-900/95 backdrop-blur">
          <div>
            <div className="text-xs uppercase tracking-wider text-slate-400">Purchase slip</div>
            <div className="text-lg font-bold leading-tight">
              {item?.po_number ? `PO ${item.po_number}` : item?.work_order_id || "Review & sign"}
            </div>
            <div className="text-xs text-slate-500">
              {item?.supplier || "No supplier"} · {item?.department || "—"}
            </div>
          </div>
          <button
            type="button"
            className="btn-ghost !px-2"
            onClick={onClose}
            disabled={busy}
            aria-label="Close window"
          >
            <X size={16} />
          </button>
        </div>

        {/* Step pills */}
        <div className="px-5 pt-4 flex items-center gap-2 text-xs">
          {[
            [1, "1 · View the request"],
            [2, "2 · Sign the request"],
          ].map(([n, label]) => (
            <button
              key={n}
              type="button"
              onClick={() => setStep(n)}
              className={`px-3 py-1.5 rounded-full border font-medium ${
                step === n
                  ? "bg-brand-700 text-white border-brand-700"
                  : "border-slate-200 dark:border-white/15 text-slate-500 hover:bg-slate-50 dark:hover:bg-white/5"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="px-5 py-4 space-y-4">
          {error && (
            <div className="rounded-lg bg-rose-50 dark:bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
              {error}
            </div>
          )}

          {step === 1 ? (
            <>
              <dl className="grid sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
                {rows.map(([k, v]) => (
                  <div key={k} className="flex gap-2">
                    <dt className="text-slate-400 w-32 shrink-0">{k}</dt>
                    <dd className="font-medium truncate">{v}</dd>
                  </div>
                ))}
              </dl>
              <div className="rounded-xl border border-slate-200 dark:border-white/10 overflow-hidden">
                <div className="px-3 py-2 text-xs font-medium text-slate-500 border-b border-slate-100 dark:border-white/5 flex justify-between items-center">
                  <span>The slip exactly as it will be filed</span>
                  <button type="button" className="text-brand-700 dark:text-cyan-300" onClick={onDownload}>
                    <Download size={12} className="inline mr-1" />
                    Download
                  </button>
                </div>
                {pdfUrl ? (
                  <iframe title="PO PDF" src={pdfUrl} className="w-full h-[26rem] bg-slate-100" />
                ) : (
                  <div className="p-6 text-sm text-slate-500">Preparing PDF…</div>
                )}
              </div>
              <div className="flex justify-end">
                <button type="button" className="btn-primary" onClick={() => setStep(2)}>
                  Next: sign the request <ArrowRight size={14} />
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="text-sm text-slate-500">
                Draw your signature once — it prints on the PDF at corporate size. Then choose who carries the signed
                slip onward.
              </p>
              <div>
                <label className="lbl">Your digital signature</label>
                <SignaturePad value={signature} onChange={setSignature} />
              </div>
              <div>
                <label className="lbl">Send signed slip to</label>
                <select value={returnTo} onChange={(e) => setReturnTo(e.target.value)} data-tour="sign-return-to">
                  <option value={a.assignee || ""}>{a.assignee ? `Sender · ${a.assignee}` : "Sender"}</option>
                  {people.map((p) => (
                    <option key={p.username} value={p.username}>
                      {p.label} ({p.role})
                    </option>
                  ))}
                </select>
                <p className="text-xs text-slate-500 mt-1">
                  They receive the signed slip and can forward it or file it with Accounts.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  className="btn-go"
                  disabled={busy || !signature}
                  data-tour="sign-send"
                  onClick={() =>
                    onDecide?.(
                      { approve: true, signature_png: signature, comment, return_to: returnTo },
                      { done: () => {} }
                    )
                  }
                >
                  <Stamp size={14} /> Sign &amp; send
                </button>
                <button
                  type="button"
                  className="btn-ghost text-sm text-amber-600 dark:text-amber-300"
                  disabled={busy}
                  onClick={() => setShowReturn((v) => !v)}
                >
                  {showReturn ? "Hide" : "Not approved — return with changes"}
                </button>
              </div>
              <p className="text-xs text-slate-500">
                Signing locks the slip: suppliers, items and prices cannot change afterwards. The person you chose gets
                it with your signature printed on the PDF.
              </p>

              {showReturn && (
                <div className="rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50/60 dark:bg-amber-500/10 p-3 space-y-2">
                  <div>
                    <label className="lbl">What must change? (required)</label>
                    <textarea
                      rows={3}
                      value={comment}
                      data-tour="sign-return"
                      onChange={(e) => setComment(e.target.value)}
                      placeholder="e.g. Quantity is wrong — match the RFQ, then send it back to me."
                    />
                  </div>
                  <button
                    className="btn-warn"
                    disabled={busy || !comment.trim()}
                    onClick={() => onDecide?.({ approve: false, comment }, { done: () => {} })}
                  >
                    Return to {a.assignee || "the technician"} with changes
                  </button>
                  <p className="text-xs text-slate-500">
                    No signature needed. {a.assignee || "The technician"} is notified, fixes the slip, and sends it to
                    the manager(s) again.
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
