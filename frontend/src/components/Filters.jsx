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

export default function Filters({ value, onChange, options = {}, extra }) {
  const v = value || {};
  const set = (k, val) => onChange({ ...v, [k]: val });
  const active = Object.entries(v).filter(([, val]) => val !== undefined && val !== null && val !== "" && !(Array.isArray(val) && !val.length));

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Filters</div>
        {active.length > 0 && (
          <button type="button" className="text-xs text-brand-700 dark:text-cyan-300 hover:underline" onClick={() => onChange({})}>
            Clear all
          </button>
        )}
      </div>
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
        <Select label="Status" field="status" value={v} set={set} options={options.status} />
        <Select label="Priority" field="priority" value={v} set={set} options={options.priority} />
        <Select label="Department" field="department" value={v} set={set} options={options.department} />
        <Select label="Assigned to" field="assigned_to" value={v} set={set} options={options.assigned_to} />
        <Select label="Location" field="location" value={v} set={set} options={options.location} />
        <Select label="Work type" field="work_type" value={v} set={set} options={options.work_type} />
        <Select label="Delay reason" field="delay_reason" value={v} set={set} options={options.delay_reason} />
        <Select label="Supplier" field="supplier" value={v} set={set} options={options.supplier} />
        {extra}
      </div>
    </div>
  );
}

function Select({ label, field, value, set, options }) {
  return (
    <div>
      <label className="lbl">{label}</label>
      <select value={value[field] || ""} onChange={(e) => set(field, e.target.value)}>
        <option value="">All</option>
        {(options || []).map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}
