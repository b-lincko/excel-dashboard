import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Columns3, Download, Plus, RefreshCw } from "lucide-react";
import { api, qs } from "../lib/api.js";
import { useLiveReload } from "../lib/live.js";
import { useAuth } from "../context/AuthContext.jsx";
import Filters from "../components/Filters.jsx";
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
  const tick = useLiveReload();
  const [filters, setFilters] = useState(() => fromSearch(loc.search, presetFlag));
  const [options, setOptions] = useState({});
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [sort, setSort] = useState(filters.sort || (presetFlag === "overdue" ? "days_overdue" : "created_date"));
  const [order, setOrder] = useState(filters.order || "desc");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [visible, setVisible] = useState(() => new Set(ALL_COLS.map((c) => c[0])));
  const [showCols, setShowCols] = useState(false);
  const [q, setQ] = useState(filters.q || "");
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
    api.get("/api/work-orders/options").then((d) => setOptions(d.options || {})).catch(() => {});
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

  function toggleSort(key) {
    if (sort === key) setOrder(order === "asc" ? "desc" : "asc");
    else {
      setSort(key);
      setOrder("asc");
    }
  }

  const pages = Math.max(1, Math.ceil(total / pageSize));
  const cols = ALL_COLS.filter((c) => visible.has(c[0]));

  async function exportCsv() {
    const params = { ...filters, q, page: 1, page_size: 500, sort, order };
    const d = await api.get(`/api/work-orders${qs(params)}`);
    const header = cols.map((c) => c[1]);
    const lines = [header.join(",")];
    (d.items || []).forEach((r) => {
      lines.push(cols.map((c) => `"${String(r[c[0]] ?? "").replace(/"/g, '""')}"`).join(","));
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
                      }}
                    />
                    {l}
                  </label>
                ))}
              </div>
            )}
          </div>
          {can("create") && (
            <button className="btn-primary" onClick={() => nav("/work-orders/new")}>
              <Plus size={14} /> New work order
            </button>
          )}
        </div>
      </div>

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
          <div>
            <label className="lbl">Search</label>
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
                placeholder="ID, description, technician…"
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
                Hard search
              </button>
            </div>
          </div>
        }
      />

      {error && <div className="text-sm text-rose-600">{error}</div>}

      <div className="card overflow-hidden">
        <div className="table-wrap max-h-[70vh]">
          <table className="data">
            <thead>
              <tr>
                {cols.map(([k, l]) => (
                  <th key={k} onClick={() => toggleSort(k)} className="cursor-pointer select-none">
                    {l}
                    {sort === k ? (order === "asc" ? " ↑" : " ↓") : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.record_id || `${r._sheet}:${r._row}` || r.work_order_id}
                  onClick={() => nav(`/work-orders/${encodeURIComponent(r.record_id || r.work_order_id)}`)}
                >
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
                      ) : (
                        r[k] ?? "—"
                      )}
                    </td>
                  ))}
                </tr>
              ))}
              {!loading && !rows.length && (
                <tr>
                  <td colSpan={cols.length} className="text-center text-slate-400 py-10">
                    No work orders match the current filters.
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
