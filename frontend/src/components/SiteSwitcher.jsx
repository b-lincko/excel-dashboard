const FALLBACK = [
  { id: "", label: "All sites", kind: "all" },
  { id: "SH5-SH1", label: "SH5-SH1", kind: "sheet" },
  { id: "SH5", label: "SH5", kind: "group", group: "SH5" },
  { id: "SH5-S1", label: "Site - 1", kind: "camp", group: "SH5" },
  { id: "SH5-S2", label: "Site - 2", kind: "camp", group: "SH5" },
  { id: "SH5-S3", label: "Site - 3", kind: "camp", group: "SH5" },
  { id: "SH5-S4A", label: "Site - 4A", kind: "camp", group: "SH5" },
  { id: "SH5-S5", label: "Site - 5", kind: "camp", group: "SH5" },
  { id: "SH5-S7", label: "Site - 7", kind: "camp", group: "SH5" },
  { id: "SH1", label: "SH1", kind: "group", group: "SH1" },
  { id: "SH1-L1", label: "L1", kind: "camp", group: "SH1" },
  { id: "SH1-L2", label: "L2", kind: "camp", group: "SH1" },
  { id: "SH1-L3", label: "L3", kind: "camp", group: "SH1" },
  { id: "SH1-L4", label: "L4", kind: "camp", group: "SH1" },
  { id: "SH1-L5", label: "L5", kind: "camp", group: "SH1" },
  { id: "SH1-L7", label: "L7", kind: "camp", group: "SH1" },
  { id: "SH1-LS1", label: "LS1", kind: "camp", group: "SH1" },
  { id: "SH1-LS2", label: "LS2", kind: "camp", group: "SH1" },
  { id: "F5", label: "F5", kind: "sheet" },
  { id: "Office", label: "Office", kind: "sheet" },
  { id: "Accommodations", label: "Accommodations", kind: "sheet" },
];

function Chip({ id, label, on, onChange }) {
  return (
    <button
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
}

export default function SiteSwitcher({ value, onChange, sites }) {
  const current = value || "";
  const incoming = Array.isArray(sites) ? sites : [];
  const mapped = incoming.map((s) =>
    typeof s === "string" ? { id: s, label: s, kind: "sheet" } : { kind: s.kind || "sheet", group: s.group || "", ...s }
  );
  const raw = mapped.some((s) => s.kind === "camp") ? mapped : FALLBACK;
  const items = raw.map((s) =>
    typeof s === "string" ? { id: s, label: s, kind: "sheet" } : { kind: s.kind || "sheet", group: s.group || "", ...s }
  );
  const hasAll = items.some((s) => s.id === "" || s.label === "All sites");
  const list = hasAll ? items : [{ id: "", label: "All sites", kind: "all" }, ...items];
  const grouped = list.some((s) => s.kind === "camp" || s.kind === "group");

  if (!grouped) {
    return (
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[10px] uppercase tracking-wider text-slate-500 mr-1">Site</span>
        {list.map((s) => (
          <Chip key={s.id || "all"} id={s.id} label={s.label || s.id} on={String(current) === String(s.id)} onChange={onChange} />
        ))}
      </div>
    );
  }

  const top = list.filter((s) => s.kind === "all" || s.kind === "sheet");
  const groups = [];
  list.forEach((s) => {
    if (s.kind !== "group" && s.kind !== "camp") return;
    const g = s.group || s.label;
    if (!groups.includes(g)) groups.push(g);
  });

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[10px] uppercase tracking-wider text-slate-500 mr-1">Site</span>
        {top.map((s) => (
          <Chip key={s.id || "all"} id={s.id} label={s.label || s.id} on={String(current) === String(s.id)} onChange={onChange} />
        ))}
      </div>
      {groups.map((g) => {
        const head = list.find((s) => s.kind === "group" && (s.group === g || s.id === g));
        const camps = list.filter((s) => s.kind === "camp" && s.group === g);
        return (
          <div key={g} className="flex flex-wrap items-center gap-1.5 pl-0 sm:pl-8">
            {head ? (
              <Chip id={head.id} label={head.label || g} on={String(current) === String(head.id)} onChange={onChange} />
            ) : (
              <span className="text-[10px] uppercase tracking-wider text-slate-500 mr-1">{g}</span>
            )}
            {camps.map((s) => (
              <Chip key={s.id} id={s.id} label={s.label || s.id} on={String(current) === String(s.id)} onChange={onChange} />
            ))}
          </div>
        );
      })}
    </div>
  );
}
