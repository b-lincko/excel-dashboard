import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LayoutGrid, Plus, RotateCcw } from "lucide-react";
import { api, qs } from "../lib/api.js";
import Filters from "../components/Filters.jsx";
import WidgetBoard, { AddWidgetBar } from "../components/WidgetBoard.jsx";
import {
  DEFAULT_LAYOUT,
  loadLayout,
  newWidget,
  readDashCache,
  saveLayout,
  writeDashCache,
} from "../lib/widgets.js";

export default function Dashboard() {
  const nav = useNavigate();
  const cached = readDashCache();
  const [filters, setFilters] = useState({});
  const [options, setOptions] = useState(cached?.options || {});
  const [data, setData] = useState(cached);
  const [error, setError] = useState("");
  const [offline, setOffline] = useState(false);
  const [loading, setLoading] = useState(!cached);
  const [tick, setTick] = useState(0);
  const [layout, setLayout] = useState(loadLayout);
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const dataRef = useRef(cached);

  useEffect(() => {
    dataRef.current = data;
    if (data) writeDashCache(data);
  }, [data]);

  useEffect(() => {
    const onData = () => setTick((n) => n + 1);
    window.addEventListener("woms:data", onData);
    return () => window.removeEventListener("woms:data", onData);
  }, []);

  useEffect(() => {
    api
      .get("/api/auth/layout")
      .then((d) => {
        if (Array.isArray(d.widgets)) {
          setLayout(d.widgets);
          saveLayout(d.widgets);
        }
      })
      .catch(() => {});
  }, []);

  const load = useCallback(() => api.get(`/api/dashboard${qs(filters)}`), [filters]);

  useEffect(() => {
    let cancelled = false;
    const keep = !!dataRef.current;
    if (!keep) setLoading(true);
    load()
      .then((dash) => {
        if (cancelled) return;
        setOffline(false);
        setError("");
        setData(dash);
        if (dash.options) setOptions(dash.options);
      })
      .catch((e) => {
        if (cancelled) return;
        if (keep) return;
        setOffline(!!e.offline);
        setError(e.detail || e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [load, tick]);

  function persist(next) {
    setLayout(next);
    saveLayout(next);
    api.put("/api/auth/layout", { widgets: next }).catch(() => {});
  }

  const go = (params) => {
    const sp = new URLSearchParams();
    Object.entries({ ...filters, ...params }).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      sp.set(key, Array.isArray(value) ? value.join(",") : String(value));
    });
    const s = sp.toString();
    nav(s ? `/work-orders?${s}` : "/work-orders");
  };

  if (error && !data) {
    const excelDown = !offline && /unavailable|could not be opened|locked/i.test(String(error));
    return (
      <div className="card p-8 text-center max-w-xl mx-auto">
        <div className="text-lg font-semibold">
          {offline ? "Backend API is not running" : excelDown ? "Excel file is currently unavailable." : "Could not load the dashboard"}
        </div>
        <p className="text-sm text-slate-500 mt-2">{typeof error === "string" ? error : JSON.stringify(error)}</p>
        {offline && (
          <ol className="text-left text-sm text-slate-600 dark:text-slate-300 mt-4 space-y-1 list-decimal list-inside">
            <li>
              Run <code>run.bat</code> — it must open a window titled <b>Linkco MR API</b>.
            </li>
            <li>Leave that window open. It should say “Excel found” then “Uvicorn running on http://0.0.0.0:8000”.</li>
            <li>
              Confirm <code>file.xlsx</code> is in the same folder as <code>run.bat</code>.
            </li>
            <li>Refresh this page.</li>
          </ol>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Material Request dashboard</h1>
          <p className="text-sm text-slate-500">
            Live from Excel · {data?.as_of || "—"} · {data?.sync?.record_count ?? data?.count ?? "—"} records
            {loading ? " · updating…" : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {editing && (
            <>
              <button className="btn-outline" onClick={() => setAdding((v) => !v)}>
                <Plus size={14} /> Add widget
              </button>
              <button
                className="btn-outline"
                onClick={() => {
                  persist(DEFAULT_LAYOUT.map((w) => ({ ...w })));
                }}
              >
                <RotateCcw size={14} /> Reset
              </button>
            </>
          )}
          <button className={editing ? "btn-primary" : "btn-outline"} onClick={() => { setEditing((v) => !v); setAdding(false); }}>
            <LayoutGrid size={14} />
            {editing ? "Done" : "Customize"}
          </button>
        </div>
      </div>

      <Filters value={filters} onChange={setFilters} options={options} />

      {adding && editing && (
        <AddWidgetBar
          onAdd={(type, extras) => persist([...layout, newWidget(type, extras)])}
          onClose={() => setAdding(false)}
        />
      )}

      {!data && loading ? (
        <div className="card p-8 text-center text-slate-500">Loading dashboard…</div>
      ) : layout.length ? (
        <WidgetBoard data={data} recent={data?.recent} go={go} layout={layout} editing={editing} onChange={persist} />
      ) : (
        <div className="card p-8 text-center text-slate-500">
          No widgets on this dashboard.
          <div className="mt-3">
            <button
              className="btn-primary"
              onClick={() => {
                setEditing(true);
                setAdding(true);
              }}
            >
              <Plus size={14} /> Add a widget
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
