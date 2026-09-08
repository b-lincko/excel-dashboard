import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Bookmark, Columns3, Download, Plus, RefreshCw } from "lucide-react";
import { api, qs } from "../lib/api.js";
import { useLiveReload } from "../lib/live.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";
import Filters from "../components/Filters.jsx";
import SiteSwitcher from "../components/SiteSwitcher.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

const ALL_COLS = [
  ["work_order_id", "IM WO #"],
  ["department", "Site"],
  ["created_date", "MR Received"],
  ["description", "Material / Description"],
  ["location", "Asset"],
  ["assigned_to", "Assigned To"],
  ["work_type", "Purchase Type"],
  ["priority", "Priority"],
  ["status", "Status"],
  ["issue", "Delivery"],
  ["supplier", "Supplier"],
  ["line_count", "Items"],
  ["po_number", "PO No"],
  ["due_date", "Due"],
  ["scheduled_date", "PO / RFQ Date"],
  ["closed_date", "ETA"],
  ["remarks", "Remarks"],
  ["aging_days", "Age (d)"],
  ["days_overdue", "Overdue (d)"],
];

function fromSearch(search, presetFlag) {
  const sp = new URLSearchParams(search);
  const obj = {};
  [
    "q",
    "period",
    "date_from",
    "date_to",
    "status",
    "priority",
    "department",
    "location",
    "assigned_to",
    "work_type",
    "delay_reason",
    "supplier",
    "issue",
    "flag",
    "aging",
    "aging_min",
    "watched",
    "reason",
    "year",
    "week",
    "month",
    "sort",
    "order",
  ].forEach((k) => {
    if (sp.get(k)) obj[k] = sp.get(k);
  });
  if (presetFlag && !obj.flag) obj.flag = presetFlag;
  return obj;
}

export default function WorkOrders({ presetFlag, title = "Work Orders" }) {
  const loc = useLocation();
  const nav = useNavigate();
  const { can } = useAuth();
  const { toast, ask } = useUi();
  const tick = useLiveReload();
  const [filters, setFilters] = useState(() => fromSearch(loc.search, presetFlag));
  const [options, setOptions] = useState({});
  const [sites, setSites] = useState([]);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [sort, setSort] = useState(filters.sort || (presetFlag === "overdue" ? "days_overdue" : "created_date"));
  const [order, setOrder] = useState(filters.order || "desc");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [visible, setVisible] = useState(() => {
    try {
      const raw = localStorage.getItem("woms.columns");
      const keys = raw ? JSON.parse(raw) : null;
      if (Array.isArray(keys) && keys.length) return new Set(keys.filter((k) => ALL_COLS.some((c) => c[0] === k)));
    } catch {
      /* ignore */
    }
    return new Set(ALL_COLS.map((c) => c[0]));
  });
  const [showCols, setShowCols] = useState(false);
  const [q, setQ] = useState(filters.q || "");
  const [selected, setSelected] = useState(() => new Set());
  const [views, setViews] = useState([]);
  const [viewName, setViewName] = useState("");
  const [viewShared, setViewShared] = useState(false);
  const [showSaveView, setShowSaveView] = useState(false);
  const [bulkAssign, setBulkAssign] = useState("");
  const [bulkStatus, setBulkStatus] = useState("");
  const [bulkRemark, setBulkRemark] = useState("");
  const [bulkBusy, setBulkBusy] = useState(false);
  const [cursor, setCursor] = useState(-1);
  const hadRows = useRef(false);

  useEffect(() => {
    const next = fromSearch(loc.search, presetFlag);
    setFilters(next);
    setQ(next.q || "");
    setPage(1);
  }, [loc.search, presetFlag]);

  useEffect(() => {
    const t = window.setTimeout(() => {
      setFilters((f) => {
        if ((f.q || "") === q) return f;
        setPage(1);
        return { ...f, q };
      });
    }, 400);
    return () => window.clearTimeout(t);
  }, [q]);

  useEffect(() => {
    api.get("/api/work-orders/options").then((d) => {
      setOptions(d.options || {});
      setSites(d.sites || []);
    }).catch(() => {});
    api.get("/api/views").then((d) => setViews(d.items || [])).catch(() => {});
  }, []);

  function load(silent = false) {
    if (!silent) setLoading(true);
    if (!silent) setError("");
    const params = { ...filters, q, sort, order, page, page_size: pageSize };
    api
      .get(`/api/work-orders${qs(params)}`)
      .then((d) => {
        setRows(d.items || []);
        setTotal(d.total || 0);
        setError("");
        hadRows.current = true;
      })
      .catch((e) => {
        if (!silent) setError(e.message);
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load(hadRows.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, sort, order, page, pageSize]);

  useEffect(() => {
    if (tick) load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick]);

  useEffect(() => {
    setCursor(-1);
  }, [rows]);

  useEffect(() => {
    function onKey(e) {
      const tag = (e.target?.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select" || e.target?.isContentEditable) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        setCursor((n) => Math.min(rows.length - 1, (n < 0 ? 0 : n + 1)));
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        setCursor((n) => Math.max(0, n < 0 ? 0 : n - 1));
      } else if (e.key === "Enter" && cursor >= 0 && rows[cursor]) {
        e.preventDefault();
        const r = rows[cursor];
        nav(`/work-orders/${encodeURIComponent(r.record_id || r.work_order_id)}`);
      } else if (e.key === "x" && can("edit") && cursor >= 0 && rows[cursor]?.record_id) {
        e.preventDefault();
        const id = rows[cursor].record_id;
        toggleRow(id, !selected.has(id));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows, cursor, selected, can, nav]);

  function toggleSort(key) {
    if (sort === key) setOrder(order === "asc" ? "desc" : "asc");
    else {
      setSort(key);
      setOrder("asc");
    }
  }

  const pages = Math.max(1, Math.ceil(total / pageSize));
  const cols = ALL_COLS.filter((c) => visible.has(c[0]));
  const pageIds = rows.map((r) => r.record_id).filter(Boolean);
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id));

  function toggleRow(id, on) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  function togglePage(on) {
    setSelected((prev) => {
      const next = new Set(prev);
      pageIds.forEach((id) => {
        if (on) next.add(id);
        else next.delete(id);
      });
      return next;
    });
  }

  function applyView(view) {
    const next = { ...(view.filters || {}) };
    if (presetFlag && !next.flag) next.flag = presetFlag;
    setFilters(next);
    setQ(next.q || "");
    setPage(1);
  }

  async function saveView() {
    const name = viewName.trim();
    if (!name) return;
    try {
      const d = await api.post("/api/views", { name, filters: { ...filters, q }, shared: viewShared });
      setViews((list) => [d.item, ...list.filter((v) => v.id !== d.item.id)]);
      setViewName("");
      setShowSaveView(false);
      toast(viewShared ? "Shared view saved" : "View saved", "success");
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function removeView(view) {
    const ok = await ask({ title: `Delete “${view.name}”?`, body: "This saved filter set will be removed.", confirmLabel: "Delete", danger: true });
    if (!ok) return;
    await api.del(`/api/views/${view.id}`);
    setViews((list) => list.filter((v) => v.id !== view.id));
  }

  async function runBulk() {
    const ids = [...selected];
    if (!ids.length) return;
    if (!bulkAssign && !bulkStatus && !bulkRemark.trim()) {
      toast("Choose an assignee, status, or remark.", "error");
      return;
    }
    const ok = await ask({
      title: `Update ${ids.length} work order${ids.length === 1 ? "" : "s"}?`,
      body: "The same assignee, status and/or remark will be applied to every selected material request. Remarks are appended.",
      confirmLabel: "Apply",
    });
    if (!ok) return;
    setBulkBusy(true);
    try {
      const body = { ids, append_remarks: true, force: true };
      if (bulkAssign) body.assigned_to = bulkAssign;
      if (bulkStatus) body.status = bulkStatus;
      if (bulkRemark.trim()) body.remarks = bulkRemark.trim();
      const d = await api.post("/api/work-orders/bulk", body);
      toast(`Updated ${d.updated} record${d.updated === 1 ? "" : "s"}`, d.excel_backup_ok === false ? "error" : "success");
      if (d.excel_backup_ok === false) {
        toast(d.excel_backup_error || "Saved in the database. Excel backup failed.", "error");
      }
      setSelected(new Set());
      setBulkRemark("");
      load();
    } catch (e) {
      toast(e.message || "Bulk update failed", "error");
    } finally {
      setBulkBusy(false);
    }
  }

  async function exportCsv() {
    const params = { ...filters, q, page: 1, page_size: 500, sort, order };
    const d = await api.get(`/api/work-orders${qs(params)}`);
    const header = cols.map((c) => c[1]);
    const lines = [header.join(",")];
    (d.items || []).forEach((r) => {
      lines.push(
        cols
          .map((c) => {
            const val = c[0] === "department" ? r.site_display || r.camp_site_label || r[c[0]] : r[c[0]];
            return `"${String(val ?? "").replace(/"/g, '""')}"`;
          })
          .join(",")
      );
    });
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "work_orders.csv";
    a.click();
  }

  const subtitle = useMemo(() => {
    if (filters.reason) return `Reason: ${filters.reason}`;
    if (filters.aging) return `Aging bucket: ${filters.aging}`;
    return `${total} matching records`;
  }, [filters, total]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          <p className="text-sm text-slate-500">{subtitle}</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-outline" onClick={() => load()}>
            <RefreshCw size={14} /> Refresh
          </button>
          <button className="btn-outline" onClick={exportCsv}>
            <Download size={14} /> Export CSV
          </button>
          <button className="btn-outline" onClick={() => setShowSaveView((s) => !s)}>
            <Bookmark size={14} /> Save view
          </button>
          <div className="relative">
            <button className="btn-outline" onClick={() => setShowCols((s) => !s)}>
              <Columns3 size={14} /> Columns
            </button>
            {showCols && (
              <div className="absolute right-0 mt-2 w-56 card p-3 z-20 space-y-1">
                {ALL_COLS.map(([k, l]) => (
                  <label key={k} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="w-auto"
                      checked={visible.has(k)}
                      onChange={() => {
                        const n = new Set(visible);
                        if (n.has(k)) n.delete(k);
                        else n.add(k);
                        setVisible(n);
                        try {
                          localStorage.setItem("woms.columns", JSON.stringify([...n]));
                        } catch {
                          /* ignore */
                        }
                      }}
                    />
                    {l}
                  </label>
                ))}
              </div>
            )}
          </div>
          {can("create") && (
            <button className="btn-primary" data-tour="wo-new" onClick={() => nav("/work-orders/new")}>
              <Plus size={14} /> New work order
            </button>
          )}
        </div>
      </div>

      <SiteSwitcher
        value={filters.department || ""}
        sites={sites}
        onChange={(id) => {
          setFilters((f) => {
            const next = { ...f, department: id || undefined };
            if (presetFlag && !next.flag) next.flag = presetFlag;
            return next;
          });
          setPage(1);
        }}
      />

      <Filters
        value={filters}
        onChange={(v) => {
          const next = { ...v };
          if (presetFlag && !next.flag) next.flag = presetFlag;
          setFilters(next);
          if (!next.q) setQ("");
          setPage(1);
        }}
        options={options}
        extra={
          <div className="flex gap-2">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setFilters((f) => ({ ...f, q }));
                  setPage(1);
                  load();
                }
              }}
              placeholder="Search ID, material, technician…"
              aria-label="Search work orders"
            />
            <button
              type="button"
              className="btn-outline whitespace-nowrap"
              onClick={() => {
                setFilters((f) => ({ ...f, q }));
                setPage(1);
                load();
              }}
            >
              Search
            </button>
          </div>
        }
      />

      {showSaveView && (
        <div className="card p-4 flex flex-wrap items-end gap-3">
          <div className="min-w-[200px] flex-1">
            <label className="lbl">View name</label>
            <input value={viewName} onChange={(e) => setViewName(e.target.value)} placeholder='e.g. my OPEN at F5' />
          </div>
          <label className="flex items-center gap-2 text-sm pb-2">
            <input type="checkbox" className="w-auto" checked={viewShared} onChange={(e) => setViewShared(e.target.checked)} />
            Share with team
          </label>
          <button className="btn-primary" onClick={saveView} disabled={!viewName.trim()}>
            Save current filters
          </button>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {views.map((v) => (
          <div key={v.id} className="inline-flex items-center gap-1 rounded-full border border-slate-200 dark:border-white/10 px-2 py-1 text-xs">
            <button type="button" className="hover:underline" onClick={() => applyView(v)}>
              {v.name}
              {v.shared ? " · shared" : ""}
            </button>
            {v.mine && (
              <button type="button" className="text-slate-400 hover:text-rose-600" onClick={() => removeView(v)} aria-label={`Delete ${v.name}`}>
                ×
              </button>
            )}
          </div>
        ))}
        <button
          type="button"
          className={`rounded-full px-2 py-1 text-xs border ${filters.watched ? "bg-brand-700 text-white border-brand-700" : "border-slate-200 dark:border-white/10"}`}
          onClick={() => {
            setFilters((f) => ({ ...f, watched: f.watched ? "" : "1" }));
            setPage(1);
          }}
        >
          Following
        </button>
      </div>

      {can("edit") && selected.size > 0 && (
        <div className="card p-3 flex flex-wrap items-end gap-3">
          <div className="text-sm font-medium pb-2">{selected.size} selected</div>
          <div>
            <label className="lbl">Assign to</label>
            <select className="w-auto min-w-[140px]" value={bulkAssign} onChange={(e) => setBulkAssign(e.target.value)} aria-label="Bulk assign">
              <option value="">— keep —</option>
              {(options.assigned_to || []).map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="lbl">Status</label>
            <select className="w-auto min-w-[140px]" value={bulkStatus} onChange={(e) => setBulkStatus(e.target.value)}>
              <option value="">— keep —</option>
              {(options.status || []).map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1 min-w-[200px]">
            <label className="lbl">Append remark (@name to ping)</label>
            <input value={bulkRemark} onChange={(e) => setBulkRemark(e.target.value)} placeholder="Same note on every selected row" />
          </div>
          <button className="btn-primary" onClick={runBulk} disabled={bulkBusy}>
            {bulkBusy ? "Saving…" : "Apply"}
          </button>
          <button className="btn-outline" onClick={() => setSelected(new Set())} disabled={bulkBusy}>
            Clear
          </button>
        </div>
      )}

      {error && <div className="text-sm text-rose-600">{error}</div>}

      <div className="card overflow-hidden" data-tour="wo-list">
        <div className="table-wrap max-h-[70vh]">
          <table className="data">
            <thead>
              <tr>
                {can("edit") && (
                  <th className="w-8">
                    <input
                      type="checkbox"
                      className="w-auto"
                      checked={allPageSelected}
                      onChange={(e) => togglePage(e.target.checked)}
                      aria-label="Select all on this page"
                    />
                  </th>
                )}
                {cols.map(([k, l]) => (
                  <th key={k} onClick={() => toggleSort(k)} className="cursor-pointer select-none">
                    {l}
                    {sort === k ? (order === "asc" ? " ↑" : " ↓") : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr
                  key={r.record_id || `${r._sheet}:${r._row}` || r.work_order_id}
                  className={cursor === i ? "bg-sky-50/80 dark:bg-sky-500/10" : ""}
                  onClick={() => nav(`/work-orders/${encodeURIComponent(r.record_id || r.work_order_id)}`)}
                >
                  {can("edit") && (
                    <td onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        className="w-auto"
                        checked={!!r.record_id && selected.has(r.record_id)}
                        disabled={!r.record_id}
                        onChange={(e) => toggleRow(r.record_id, e.target.checked)}
                        aria-label={`Select ${r.work_order_id || r.record_id}`}
                      />
                    </td>
                  )}
                  {cols.map(([k]) => (
                    <td key={k} className={k === "description" || k === "remarks" ? "max-w-[280px] truncate" : ""}>
                      {k === "status" || k === "priority" ? (
                        <StatusBadge value={r[k]} />
                      ) : k.endsWith("_date") ? (
                        (r[k] || "").slice(0, 16)
                      ) : k === "work_order_id" ? (
                        <span className="font-mono text-xs font-semibold">{r[k]}</span>
                      ) : k === "days_overdue" ? (
                        r[k] ? <span className="text-rose-600 font-semibold">{r[k]}</span> : "—"
                      ) : k === "department" ? (
                        r.site_display || r.camp_site_label || r[k] || "—"
                      ) : (
                        r[k] ?? "—"
                      )}
                    </td>
                  ))}
                </tr>
              ))}
              {loading && !rows.length && (
                <tr>
                  <td colSpan={cols.length + (can("edit") ? 1 : 0)} className="py-8">
                    <div className="space-y-2 px-2">
                      <div className="skel h-8" />
                      <div className="skel h-8" />
                      <div className="skel h-8" />
                    </div>
                  </td>
                </tr>
              )}
              {!loading && !rows.length && (
                <tr>
                  <td colSpan={cols.length + (can("edit") ? 1 : 0)} className="text-center py-12">
                    <div className="text-slate-500">No material requests match.</div>
                    <div className="mt-3 flex justify-center gap-2">
                      <button
                        type="button"
                        className="btn-outline"
                        onClick={() => {
                          setFilters(presetFlag ? { flag: presetFlag } : {});
                          setQ("");
                          setPage(1);
                        }}
                      >
                        Clear filters
                      </button>
                      {can("create") && (
                        <button type="button" className="btn-primary" onClick={() => nav("/work-orders/new")}>
                          New work order
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between px-4 py-3 text-sm border-t border-slate-100 dark:border-white/5">
          <div className="text-slate-500">
            {loading ? "Loading…" : `Showing ${(page - 1) * pageSize + (rows.length ? 1 : 0)}–${(page - 1) * pageSize + rows.length} of ${total}`}
          </div>
          <div className="flex items-center gap-2">
            <select
              className="w-auto"
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(1);
              }}
            >
              {[10, 25, 50, 100].map((n) => (
                <option key={n} value={n}>
                  {n} / page
                </option>
              ))}
            </select>
            <button className="btn-outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Prev
            </button>
            <span>
              {page} / {pages}
            </span>
            <button className="btn-outline" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
