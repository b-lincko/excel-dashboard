import { useMemo, useState } from "react";
import { SlidersHorizontal, X } from "lucide-react";

const PERIODS = [
  { id: "", label: "All time" },
  { id: "today", label: "Today" },
  { id: "yesterday", label: "Yesterday" },
  { id: "this_week", label: "This week" },
  { id: "last_week", label: "Last week" },
  { id: "this_month", label: "This month" },
  { id: "last_month", label: "Last month" },
  { id: "this_quarter", label: "This quarter" },
  { id: "this_year", label: "This year" },
  { id: "last_year", label: "Last year" },
  { id: "custom", label: "Custom range" },
];

const SELECTS = [
  ["status", "Status"],
  ["priority", "Priority"],
  ["department", "Site"],
  ["assigned_to", "Assigned to"],
  ["location", "Location"],
  ["work_type", "Work type"],
  ["delay_reason", "Delivery status"],
  ["supplier", "Supplier"],
];

const HIDDEN = new Set(["sort", "order", "page", "page_size", "flag", "q", "watched"]);

function chipLabel(key, val) {
  if (key === "period") return PERIODS.find((p) => p.id === val)?.label || val;
  if (key === "date_from") return `From ${val}`;
  if (key === "date_to") return `To ${val}`;
  const named = SELECTS.find(([k]) => k === key);
  return `${named ? named[1] : key}: ${val}`;
}

export default function Filters({ value, onChange, options = {}, extra, defaultOpen = false }) {
  const v = value || {};
  const [open, setOpen] = useState(!!defaultOpen);
  const set = (k, val) => onChange({ ...v, [k]: val });

  const chips = useMemo(() => {
    return Object.entries(v).filter(([k, val]) => {
      if (HIDDEN.has(k)) return false;
      if (val === undefined || val === null || val === "") return false;
      if (Array.isArray(val) && !val.length) return false;
      return true;
    });
  }, [v]);

  function clearKey(key) {
    const next = { ...v };
    delete next[key];
    if (key === "period") {
      delete next.date_from;
      delete next.date_to;
    }
    onChange(next);
  }

  return (
    <div className="space-y-2" data-tour="filters">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn-outline !py-1.5 !px-2.5 text-xs" onClick={() => setOpen((s) => !s)}>
          <SlidersHorizontal size={14} />
          Filters
          {chips.length ? <span className="ml-1 rounded-full bg-brand-700 text-white px-1.5 text-[10px]">{chips.length}</span> : null}
        </button>
        {chips.map(([k, val]) => (
          <button
            key={k}
            type="button"
            className="inline-flex items-center gap-1 rounded-full border border-slate-200 dark:border-white/10 bg-white dark:bg-ink-800 px-2.5 py-1 text-xs font-medium"
            onClick={() => clearKey(k)}
            title="Remove filter"
          >
            {chipLabel(k, val)}
            <X size={12} className="text-slate-400" />
          </button>
        ))}
        {chips.length > 0 && (
          <button type="button" className="text-xs text-brand-700 dark:text-cyan-300 hover:underline" onClick={() => onChange({})}>
            Clear all
          </button>
        )}
        {extra && <div className="ml-auto min-w-[220px] flex-1 max-w-md">{extra}</div>}
      </div>

      {open && (
        <div className="card p-4">
          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-3">
            <div>
              <label className="lbl">Period</label>
              <select value={v.period || ""} onChange={(e) => set("period", e.target.value)}>
                {PERIODS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            {v.period === "custom" && (
              <>
                <div>
                  <label className="lbl">From</label>
                  <input type="date" value={v.date_from || ""} onChange={(e) => set("date_from", e.target.value)} />
                </div>
                <div>
                  <label className="lbl">To</label>
                  <input type="date" value={v.date_to || ""} onChange={(e) => set("date_to", e.target.value)} />
                </div>
              </>
            )}
            {SELECTS.map(([field, label]) => (
              <div key={field}>
                <label className="lbl">{label}</label>
                <select value={v[field] || ""} onChange={(e) => set(field, e.target.value)}>
                  <option value="">All</option>
                  {(options[field] || []).map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
