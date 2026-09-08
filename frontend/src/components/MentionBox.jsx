import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api.js";

function mentionAt(text, caret) {
  const before = String(text || "").slice(0, caret);
  const m = before.match(/(^|[\s])@([A-Za-z0-9._-]*)$/);
  if (!m) return null;
  const query = m[2] || "";
  const start = before.length - query.length - 1;
  return { start, query };
}

export default function MentionBox({ value, onChange, people, placeholder, rows = 1, disabled, className = "" }) {
  const ref = useRef(null);
  const [loaded, setLoaded] = useState(people || []);
  const [open, setOpen] = useState(false);
  const [hint, setHint] = useState(null);
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    if (people?.length) {
      setLoaded(people);
      return;
    }
    api
      .get("/api/chat/people")
      .then((d) => setLoaded(d.items || []))
      .catch(() => {});
  }, [people]);

  const matches = useMemo(() => {
    if (!hint) return [];
    const q = hint.query.toLowerCase();
    return (loaded || [])
      .filter((p) => {
        const u = String(p.username || "").toLowerCase();
        const n = String(p.full_name || "").toLowerCase();
        return !q || u.includes(q) || n.includes(q);
      })
      .slice(0, 8);
  }, [hint, loaded]);

  function apply(person) {
    const el = ref.current;
    const caret = el ? el.selectionStart : String(value || "").length;
    const found = mentionAt(value || "", caret);
    if (!found) return;
    const name = person.username;
    const next = `${(value || "").slice(0, found.start)}@${name} ${(value || "").slice(caret)}`;
    onChange(next);
    setOpen(false);
    setHint(null);
    requestAnimationFrame(() => {
      const pos = found.start + name.length + 2;
      el?.focus();
      el?.setSelectionRange(pos, pos);
    });
  }

  function onInput(e) {
    const text = e.target.value;
    onChange(text);
    const found = mentionAt(text, e.target.selectionStart);
    setHint(found);
    setOpen(!!found);
    setIdx(0);
  }

  function onKey(e) {
    if (!open || !matches.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIdx((n) => (n + 1) % matches.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setIdx((n) => (n - 1 + matches.length) % matches.length);
    } else if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      apply(matches[idx] || matches[0]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  const Tag = rows > 1 ? "textarea" : "input";
  return (
    <div className={`relative ${className}`}>
      <Tag
        ref={ref}
        rows={rows > 1 ? rows : undefined}
        value={value || ""}
        disabled={disabled}
        placeholder={placeholder}
        autoComplete="off"
        onChange={onInput}
        onKeyDown={onKey}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
      />
      {open && matches.length > 0 && (
        <div className="absolute left-0 right-0 top-full z-30 mt-1 card p-1 max-h-56 overflow-auto">
          {matches.map((p, i) => (
            <button
              key={p.username}
              type="button"
              className={`w-full text-left px-3 py-1.5 rounded-lg text-sm ${i === idx ? "bg-slate-100 dark:bg-white/10" : "hover:bg-slate-50 dark:hover:bg-white/5"}`}
              onMouseDown={(e) => {
                e.preventDefault();
                apply(p);
              }}
            >
              <span className="font-medium">@{p.username}</span>
              {p.full_name ? <span className="text-slate-500"> · {p.full_name}</span> : ""}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
