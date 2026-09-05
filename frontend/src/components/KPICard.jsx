export default function KPICard({ label, value, hint, accent = "brand", onClick, icon: Icon }) {
  const accents = {
    brand: "from-brand-700 to-cyan-600",
    emerald: "from-emerald-600 to-teal-500",
    amber: "from-amber-500 to-orange-500",
    rose: "from-rose-600 to-pink-500",
    indigo: "from-indigo-600 to-violet-500",
    slate: "from-slate-600 to-slate-500",
    sky: "from-sky-600 to-cyan-500",
  };
  return (
    <button
      type="button"
      onClick={onClick}
      className="card kpi-click p-4 text-left w-full"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wider font-semibold text-slate-500 dark:text-slate-400">
            {label}
          </div>
          <div className="mt-1 text-2xl font-bold tracking-tight">{value ?? "—"}</div>
          {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
        </div>
        {Icon && (
          <div className={`h-10 w-10 rounded-xl bg-gradient-to-br ${accents[accent]} text-white grid place-items-center shadow`}>
            <Icon size={18} />
          </div>
        )}
      </div>
    </button>
  );
}
