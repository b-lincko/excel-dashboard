import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";

const PAGES = [
  { id: "dash", label: "Dashboard", hint: "g d", to: "/", page: "dashboard" },
  { id: "wo", label: "Work orders", hint: "g w", to: "/work-orders", page: "work_orders" },
  { id: "queue", label: "Action queue", hint: "g q", to: "/queue", page: "queue" },
  { id: "new", label: "New material request", hint: "n", to: "/work-orders/new", need: "create" },
  { id: "chat", label: "Chat", hint: "g c", to: "/chat", page: "chat" },
  { id: "materials", label: "Materials", to: "/materials", page: "materials" },
  { id: "guide", label: "Guide & shortcuts", hint: "?", to: "/guide" },
  { id: "settings", label: "Settings", to: "/settings", need: "settings" },
];

export default function CommandPalette({ open, onClose }) {
  const nav = useNavigate();
  const { can, canPage } = useAuth();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState({ orders: [], suppliers: [], materials: [], people: [], sites: [] });
  const [idx, setIdx] = useState(0);
  const inputRef = useRef(null);

  const pages = useMemo(
    () =>
      PAGES.filter((p) => {
        if (p.need && !can(p.need)) return false;
        if (p.page && !canPage(p.page)) return false;
        const needle = q.trim().toLowerCase();
        if (!needle) return true;
        return p.label.toLowerCase().includes(needle);
      }),
    [can, canPage, q]
  );

  const rows = useMemo(() => {
    const out = pages.map((p) => ({ ...p, kind: "page" }));
    (hits.orders || []).forEach((o) =>
      out.push({
        id: `o-${o.record_id}`,
        kind: "order",
        label: o.label,
        hint: o.hint,
        to: `/work-orders/${encodeURIComponent(o.record_id)}`,
      })
    );
    (hits.suppliers || []).forEach((s) =>
      out.push({
        id: `s-${s.label}`,
        kind: "supplier",
        label: s.label,
        hint: "Supplier",
        to: `/work-orders?q=${encodeURIComponent(s.label)}`,
      })
    );
    (hits.materials || []).forEach((m) =>
      out.push({
        id: `m-${m.label}`,
        kind: "material",
        label: m.label,
        hint: m.hint,
        to: `/work-orders?q=${encodeURIComponent(m.label)}`,
      })
    );
    (hits.people || []).forEach((p) =>
      out.push({
        id: `p-${p.username}`,
        kind: "person",
        label: p.full_name || p.label,
        hint: p.username,
        to: `/work-orders?assigned_to=${encodeURIComponent(p.full_name || p.label)}`,
      })
    );
    (hits.sites || []).forEach((s) =>
      out.push({
        id: `site-${s.id || s.label}`,
        kind: "site",
        label: s.label,
        hint: s.hint || "Site",
        to: `/work-orders?department=${encodeURIComponent(s.id || s.label)}`,
      })
    );
    return out.slice(0, 18);
  }, [pages, hits]);

  useEffect(() => {
    if (!open) return undefined;
    setQ("");
    setHits({ orders: [], suppliers: [], materials: [], people: [], sites: [] });
    setIdx(0);
    const t = window.setTimeout(() => inputRef.current?.focus(), 20);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const query = q.trim();
    if (query.length < 1) {
      setHits({ orders: [], suppliers: [], materials: [], people: [], sites: [] });
      return undefined;
    }
    const timer = window.setTimeout(() => {
      api
        .get(`/api/work-orders/suggest?q=${encodeURIComponent(query)}&limit=6`)
        .then((d) => setHits(d.groups || {}))
        .catch(() => {});
    }, 160);
    return () => window.clearTimeout(timer);
  }, [q, open]);

  useEffect(() => {
    setIdx(0);
  }, [rows.length, q]);

  function go(row) {
    if (!row?.to) return;
    onClose();
    nav(row.to);
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 grid place-items-start bg-black/40 p-4 pt-[12vh]" onClick={onClose}>
      <div className="card w-full max-w-lg overflow-hidden" onClick={(e) => e.stopPropagation()} data-tour="command">
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Jump to a page, WO, supplier, item, person, or site…"
          className="rounded-none border-0 border-b border-slate-200 dark:border-white/10 focus:ring-0"
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
            else if (e.key === "ArrowDown") {
              e.preventDefault();
              setIdx((n) => (n + 1) % Math.max(rows.length, 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setIdx((n) => (n - 1 + rows.length) % Math.max(rows.length, 1));
            } else if (e.key === "Enter") {
              e.preventDefault();
              go(rows[idx] || rows[0]);
            }
          }}
        />
        <div className="max-h-80 overflow-auto p-1">
          {rows.map((row, i) => (
            <button
              key={row.id}
              type="button"
              className={`w-full text-left px-3 py-2 rounded-lg text-sm flex items-center justify-between gap-3 ${
                i === idx ? "bg-slate-100 dark:bg-white/10" : "hover:bg-slate-50 dark:hover:bg-white/5"
              }`}
              onMouseDown={(e) => {
                e.preventDefault();
                go(row);
              }}
            >
              <span>
                <span className="font-medium">{row.label}</span>
                {row.hint ? <span className="text-slate-500"> · {row.hint}</span> : null}
              </span>
              <span className="text-[10px] uppercase tracking-wider text-slate-400">{row.kind}</span>
            </button>
          ))}
          {!rows.length && <div className="px-3 py-6 text-sm text-slate-500 text-center">No matches.</div>}
        </div>
        <div className="px-3 py-2 text-[11px] text-slate-400 border-t border-slate-100 dark:border-white/5">
          Ctrl/⌘+K · ↑↓ · Enter · Esc
        </div>
      </div>
    </div>
  );
}
