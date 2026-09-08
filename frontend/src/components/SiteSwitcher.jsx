const FALLBACK = [
  { id: "", label: "All sites" },
  { id: "SH5-SH1", label: "SH5-SH1" },
  { id: "F5", label: "F5" },
  { id: "Office", label: "Office" },
  { id: "Accommodations", label: "Accommodations" },
];

export default function SiteSwitcher({ value, onChange, sites }) {
  const current = value || "";
  const items = Array.isArray(sites) && sites.length ? sites : FALLBACK;
  const list = items.some((s) => s.id === "" || s.label === "All sites")
    ? items
    : [{ id: "", label: "All sites" }, ...items];

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-[10px] uppercase tracking-wider text-slate-500 mr-1">Site</span>
      {list.map((s) => {
        const id = s.id ?? s;
        const label = s.label || s.id || s;
        const on = String(current) === String(id);
        return (
          <button
            key={id || "all"}
            type="button"
            onClick={() => onChange(id)}
            className={`px-2.5 py-1 rounded-full text-xs font-semibold border ${
              on
                ? "bg-brand-700 text-white border-brand-700"
                : "border-slate-200 dark:border-white/10 text-slate-600 dark:text-slate-300 hover:border-brand-700"
            }`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
