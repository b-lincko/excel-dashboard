import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight, GitBranch, ListFilter } from "lucide-react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, qs } from "../lib/api.js";
import StatusBadge from "./StatusBadge.jsx";

const BRANCH_TONE = {
  sites: "bg-sky-50 border-sky-200 text-sky-900 dark:bg-sky-500/10 dark:border-sky-500/30 dark:text-sky-100",
  status: "bg-indigo-50 border-indigo-200 text-indigo-900 dark:bg-indigo-500/10 dark:border-indigo-500/30 dark:text-indigo-100",
  blockades: "bg-rose-50 border-rose-200 text-rose-900 dark:bg-rose-500/10 dark:border-rose-500/30 dark:text-rose-100",
  people: "bg-violet-50 border-violet-200 text-violet-900 dark:bg-violet-500/10 dark:border-violet-500/30 dark:text-violet-100",
  delivery: "bg-cyan-50 border-cyan-200 text-cyan-900 dark:bg-cyan-500/10 dark:border-cyan-500/30 dark:text-cyan-100",
  priority: "bg-amber-50 border-amber-200 text-amber-900 dark:bg-amber-500/10 dark:border-amber-500/30 dark:text-amber-100",
};

function toSearch(filter) {
  const sp = new URLSearchParams();
  Object.entries(filter || {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    sp.set(k, Array.isArray(v) ? v.join(",") : String(v));
  });
  return sp.toString();
}

function NodeCard({ node, tone, selected, onClick, size = "md" }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`mm-node ${tone} ${selected ? "is-on" : ""} ${size === "sm" ? "!px-2.5 !py-1.5" : ""}`}
    >
      <div className={`font-semibold leading-tight ${size === "sm" ? "text-xs" : "text-sm"}`}>{node.label}</div>
      <div className="text-[11px] opacity-80 tabular-nums">
        {node.value ?? 0}
        {node.open != null ? ` · ${node.open} open` : ""}
      </div>
    </button>
  );
}

export default function MindMap({ data }) {
  const nav = useNavigate();
  const [openIds, setOpenIds] = useState(() => new Set(["sites", "status", "blockades"]));
  const [selected, setSelected] = useState(null);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loadingItems, setLoadingItems] = useState(false);

  const root = data?.root;
  const branches = data?.branches || [];

  useEffect(() => {
    if (root && !selected) setSelected(root);
  }, [root, selected]);

  useEffect(() => {
    if (!selected) return undefined;
    let cancelled = false;
    setLoadingItems(true);
    api
      .get(`/api/work-orders${qs({ ...(selected.filter || {}), page_size: 8, sort: "created_date" })}`)
      .then((d) => {
        if (cancelled) return;
        setItems(d.items || []);
        setTotal(d.total || 0);
      })
      .catch(() => {
        if (!cancelled) {
          setItems([]);
          setTotal(0);
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingItems(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const chart = useMemo(() => {
    const kids = selected?.children || [];
    return kids.map((c) => ({ name: c.label, value: c.value }));
  }, [selected]);

  if (!root) return null;

  function toggle(id) {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function pick(node, branchId) {
    setSelected(node);
    if (node.children?.length && branchId) {
      setOpenIds((prev) => new Set(prev).add(branchId));
    }
  }

  function openList(filter) {
    const s = toSearch(filter);
    nav(s ? `/work-orders?${s}` : "/work-orders");
  }

  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-100 dark:border-white/5 flex items-center justify-between gap-3">
        <div>
          <div className="font-semibold flex items-center gap-2">
            <GitBranch size={16} /> Workbook mind map
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Click a node to expand and inspect it. Open the list for the matching Excel rows.
          </p>
        </div>
      </div>
      <div className="p-4 overflow-x-auto">
        <div className="flex items-start gap-6 min-w-[720px]">
          <div className="shrink-0 pt-6">
            <NodeCard
              node={root}
              tone="bg-brand-700 text-white border-brand-800"
              selected={selected?.id === root.id}
              onClick={() => pick(root)}
            />
          </div>
          <div className="flex-1 space-y-3">
            {branches.map((branch) => {
              const tone = BRANCH_TONE[branch.id] || "bg-slate-50 border-slate-200 dark:bg-white/5 dark:border-white/10";
              const expanded = openIds.has(branch.id);
              return (
                <div key={branch.id} className="flex items-start gap-3">
                  <div className="w-4 shrink-0 mt-5 h-px bg-slate-300 dark:bg-white/20" />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        className="text-slate-400 hover:text-slate-700"
                        onClick={() => toggle(branch.id)}
                        title={expanded ? "Collapse" : "Expand"}
                      >
                        <ChevronRight size={16} className={expanded ? "rotate-90 transition" : "transition"} />
                      </button>
                      <NodeCard
                        node={branch}
                        tone={tone}
                        selected={selected?.id === branch.id}
                        onClick={() => {
                          toggle(branch.id);
                          pick(branch, branch.id);
                        }}
                      />
                    </div>
                    {expanded && (
                      <div className="mt-2 ml-7 flex flex-wrap gap-2">
                        {(branch.children || []).map((child) => (
                          <NodeCard
                            key={child.id}
                            node={child}
                            tone={tone}
                            size="sm"
                            selected={selected?.id === child.id}
                            onClick={() => pick(child, branch.id)}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {selected && (
        <div className="border-t border-slate-100 dark:border-white/5 grid lg:grid-cols-2">
          <div className="p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-500">Selected</div>
                <h3 className="text-lg font-semibold">{selected.label}</h3>
                <p className="text-sm text-slate-500">
                  {selected.value ?? total} records
                  {selected.open != null ? ` · ${selected.open} open · ${selected.closed ?? 0} closed` : ""}
                </p>
              </div>
              <button className="btn-primary" onClick={() => openList(selected.filter || {})}>
                <ListFilter size={14} /> Open list
              </button>
            </div>
            <div className="h-[180px] mt-3">
              {chart.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chart} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
                    <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-25} textAnchor="end" height={48} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar
                      dataKey="value"
                      fill="#0F3D5E"
                      radius={[4, 4, 0, 0]}
                      cursor="pointer"
                      onClick={(d) => {
                        const hit = (selected.children || []).find((c) => c.label === d?.name);
                        if (hit) pick(hit);
                      }}
                    />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full grid place-items-center text-sm text-slate-400">
                  No further breakdown — open the list for row details.
                </div>
              )}
            </div>
          </div>
          <div className="p-4 border-t lg:border-t-0 lg:border-l border-slate-100 dark:border-white/5">
            <div className="text-xs uppercase tracking-wide text-slate-500 mb-2">
              {loadingItems ? "Loading rows…" : `Sample rows (${Math.min(items.length, 8)} of ${total})`}
            </div>
            <div className="table-wrap max-h-[220px]">
              <table className="data">
                <thead>
                  <tr>
                    <th>WO #</th>
                    <th>Description</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((r) => (
                    <tr
                      key={r.record_id || r.work_order_id}
                      onClick={() => nav(`/work-orders/${encodeURIComponent(r.record_id || r.work_order_id)}`)}
                    >
                      <td className="font-mono text-xs font-semibold">{r.work_order_id}</td>
                      <td className="max-w-[220px] truncate">{r.description}</td>
                      <td>
                        <StatusBadge value={r.status} />
                      </td>
                    </tr>
                  ))}
                  {!loadingItems && !items.length && (
                    <tr>
                      <td colSpan={3} className="text-center text-slate-400 py-6">
                        No matching rows.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
