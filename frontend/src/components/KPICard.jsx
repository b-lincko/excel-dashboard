export default function KPICard({ label, value, hint, accent = "brand", onClick, icon: Icon }) {
  const bars = {
    brand: "border-l-brand-600",
    emerald: "border-l-emerald-500",
    amber: "border-l-amber-500",
    rose: "border-l-rose-500",
    indigo: "border-l-indigo-500",
    slate: "border-l-slate-400",
    sky: "border-l-sky-500",
  };
  const chips = {
    brand: "bg-brand-50 text-brand-700 dark:bg-brand-700/20 dark:text-brand-100",
    emerald: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200",
    amber: "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200",
    rose: "bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-200",
    indigo: "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-200",
    slate: "bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-200",
    sky: "bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-200",
  };
  return (
    <button
      type="button"
      onClick={onClick}
      title={onClick ? "Click to view matching records" : undefined}
      className={`card p-4 text-left w-full border-l-4 ${bars[accent] || bars.brand} ${onClick ? "kpi-click" : ""}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-wider font-semibold text-slate-500 dark:text-slate-400">
            {label}
          </div>
          <div className="mt-1 text-2xl font-bold tracking-tight tabular-nums">{value ?? "—"}</div>
          {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
        </div>
        {Icon && (
          <div className={`h-9 w-9 rounded-full ${chips[accent] || chips.brand} grid place-items-center shrink-0`}>
            <Icon size={16} />
          </div>
        )}
      </div>
    </button>
  );
}
