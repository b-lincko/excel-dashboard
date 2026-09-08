import { useEffect, useMemo, useRef, useState } from "react";

function asOption(raw) {
  if (raw == null) return null;
  if (typeof raw === "string") return { value: raw, label: raw, hint: "" };
  const value = String(raw.value ?? raw.label ?? raw.username ?? "").trim();
  if (!value) return null;
  return {
    value,
    label: String(raw.label ?? raw.full_name ?? value),
    hint: String(raw.hint ?? raw.full_name ?? raw.username ?? ""),
  };
}

export default function TypeAhead({
  value,
  onChange,
  options = [],
  placeholder,
  disabled,
  allowCustom = true,
  className = "",
  "aria-label": ariaLabel,
}) {
  const ref = useRef(null);
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const [draft, setDraft] = useState(value || "");

  useEffect(() => {
    setDraft(value || "");
  }, [value]);

  const parsed = useMemo(() => options.map(asOption).filter(Boolean), [options]);
  const matches = useMemo(() => {
    const q = String(draft || "").trim().toLowerCase();
    const list = q
      ? parsed.filter((o) => o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q) || o.hint.toLowerCase().includes(q))
      : parsed;
    return list.slice(0, 12);
  }, [parsed, draft]);

  function commit(next) {
    const text = next == null ? "" : String(next);
    setDraft(text);
    onChange(text);
    setOpen(false);
  }

  function onKey(e) {
    if (e.key === "ArrowDown") {
      if (!open) {
        setOpen(true);
        return;
      }
      e.preventDefault();
      setIdx((n) => (n + 1) % Math.max(matches.length, 1));
    } else if (e.key === "ArrowUp") {
      if (!open) return;
      e.preventDefault();
      setIdx((n) => (n - 1 + matches.length) % Math.max(matches.length, 1));
    } else if (e.key === "Enter" || e.key === "Tab") {
      if (open && matches[idx]) {
        e.preventDefault();
        commit(matches[idx].value);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      setDraft(value || "");
    }
  }

  return (
    <div className={`relative ${className}`}>
      <input
        ref={ref}
        value={draft}
        disabled={disabled}
        placeholder={placeholder}
        aria-label={ariaLabel}
        autoComplete="off"
        onChange={(e) => {
          setDraft(e.target.value);
          setOpen(true);
          setIdx(0);
          if (allowCustom) onChange(e.target.value);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          setTimeout(() => {
            setOpen(false);
            if (!allowCustom) {
              const hit = parsed.find((o) => o.value === draft) || parsed.find((o) => o.value.toLowerCase() === String(draft || "").toLowerCase());
              if (hit) commit(hit.value);
              else setDraft(value || "");
            }
          }, 120);
        }}
        onKeyDown={onKey}
      />
      {open && matches.length > 0 && (
        <div className="absolute left-0 right-0 top-full z-30 mt-1 card p-1 max-h-64 overflow-auto">
          {matches.map((o, i) => (
            <button
              key={`${o.value}-${i}`}
              type="button"
              className={`w-full text-left px-3 py-1.5 rounded-lg text-sm ${i === idx ? "bg-slate-100 dark:bg-white/10" : "hover:bg-slate-50 dark:hover:bg-white/5"}`}
              onMouseDown={(e) => {
                e.preventDefault();
                commit(o.value);
              }}
            >
              <span className="font-medium">{o.label}</span>
              {o.hint && o.hint !== o.label ? <span className="text-slate-500"> · {o.hint}</span> : null}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
