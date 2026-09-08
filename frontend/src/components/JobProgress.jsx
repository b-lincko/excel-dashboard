export default function JobProgress({
  title,
  uploadPct = 0,
  applyPct = 0,
  applyLabel = "Applying backup",
  message = "",
  error = "",
  done = false,
  doneLabel = "Applied backup",
  onClose,
}) {
  const upload = Math.max(0, Math.min(100, Number(uploadPct) || 0));
  const apply = Math.max(0, Math.min(100, Number(applyPct) || 0));
  return (
    <div className="fixed inset-0 z-[95] grid place-items-center bg-black/50 p-4">
      <div className="card w-full max-w-md p-6 space-y-4" role="dialog" aria-modal="true" aria-label={title}>
        <div className="font-semibold text-lg">{title}</div>
        <Bar label="Uploading Excel" pct={upload} done={upload >= 100} />
        <Bar label={applyLabel} pct={apply} done={done || apply >= 100} />
        {message && !error && !done && <p className="text-sm text-slate-500">{message}</p>}
        {done && (
          <div className="rounded-lg bg-emerald-50 text-emerald-800 text-sm px-3 py-2 dark:bg-emerald-500/15 dark:text-emerald-100">
            {doneLabel}
          </div>
        )}
        {error && (
          <div className="rounded-lg bg-rose-50 text-rose-700 text-sm px-3 py-2 dark:bg-rose-500/15 dark:text-rose-200">
            {error}
          </div>
        )}
        {(done || error) && (
          <div className="flex justify-end">
            <button className="btn-primary" type="button" onClick={onClose}>
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function Bar({ label, pct, done }) {
  return (
    <div>
      <div className="flex justify-between text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">
        <span>{label}</span>
        <span>{done ? "Done" : `${pct}%`}</span>
      </div>
      <div className="h-2.5 rounded-full bg-slate-100 dark:bg-white/10 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${done ? "bg-emerald-500" : "bg-brand-600"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
