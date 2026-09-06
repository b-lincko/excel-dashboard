const COLORS = {
  Closed: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
  CLOSED: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
  Completed: "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-300",
  Cancelled: "bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300",
  "In Progress": "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300",
  Assigned: "bg-violet-50 text-violet-700 dark:bg-violet-500/10 dark:text-violet-300",
  Pending: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
  PLACED: "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300",
  "UNDER NTP": "bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-200",
  "UNDER GATEPASS": "bg-violet-50 text-violet-700 dark:bg-violet-500/10 dark:text-violet-300",
  "On Hold": "bg-orange-50 text-orange-700 dark:bg-orange-500/10 dark:text-orange-300",
  "ON HOLD": "bg-orange-50 text-orange-700 dark:bg-orange-500/10 dark:text-orange-300",
  Open: "bg-cyan-50 text-cyan-700 dark:bg-cyan-500/10 dark:text-cyan-300",
  OPEN: "bg-cyan-50 text-cyan-700 dark:bg-cyan-500/10 dark:text-cyan-300",
  New: "bg-teal-50 text-teal-700 dark:bg-teal-500/10 dark:text-teal-300",
  Overdue: "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300",
  Delivered: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
  "Estimation Provided": "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-300",
  "Material in Store": "bg-teal-50 text-teal-700 dark:bg-teal-500/10 dark:text-teal-300",
  Critical: "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300",
  High: "bg-orange-50 text-orange-700 dark:bg-orange-500/10 dark:text-orange-300",
  Medium: "bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-200",
  Low: "bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300",
};

export default function StatusBadge({ value }) {
  if (!value) return <span className="text-slate-400">—</span>;
  const cls = COLORS[value] || "bg-slate-100 text-slate-700 dark:bg-white/10 dark:text-slate-200";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${cls}`}>
      {value}
    </span>
  );
}
