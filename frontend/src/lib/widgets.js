export const LAYOUT_KEY = "woms_dash_layout_v1";
export const DASH_CACHE_KEY = "woms_dash_cache_v1";

export const KPI_METRICS = [
  { id: "created_today", label: "Jobs in today", accent: "brand", source: "kpis", click: { flag: "created_today" } },
  { id: "done_today", label: "Jobs done today", accent: "emerald", source: "kpis", click: { flag: "closed", period: "today" } },
  { id: "delivered_today", label: "Delivered today", accent: "sky", source: "kpis", click: { flag: "delivered" } },
  { id: "blockades", label: "Blockades", accent: "rose", source: "kpis", click: { flag: "open" } },
  { id: "in_progress", label: "In progress", accent: "indigo", source: "kpis", click: { flag: "in_progress" } },
  { id: "overdue", label: "Overdue", accent: "rose", source: "kpis", click: { flag: "overdue" } },
  { id: "total", label: "Total MRs", accent: "brand", source: "kpis", click: {} },
  { id: "open", label: "Open", accent: "sky", source: "kpis", click: { flag: "open" } },
  { id: "placed", label: "Placed", accent: "indigo", source: "kpis", click: { flag: "placed" } },
  { id: "closed", label: "Closed", accent: "emerald", source: "kpis", click: { flag: "closed" } },
  { id: "pending", label: "Pending / NTP", accent: "amber", source: "kpis", click: { flag: "pending" } },
  { id: "completion_rate", label: "Completion rate", accent: "emerald", source: "kpis", suffix: "%" },
  { id: "average_closing_days", label: "Avg close (days)", accent: "brand", source: "kpis" },
  { id: "average_aging_days", label: "Avg aging (days)", accent: "amber", source: "kpis" },
  { id: "ntp", label: "UNDER NTP", accent: "amber", source: "ops", click: { flag: "ntp" } },
  { id: "on_hold", label: "ON HOLD", accent: "amber", source: "ops", click: { flag: "on_hold" } },
  { id: "due_this_week", label: "Due this week", accent: "sky", source: "ops", click: { flag: "due_week" } },
  { id: "eta_late", label: "ETA missed", accent: "rose", source: "ops", click: { flag: "eta_late" } },
  { id: "pending_po", label: "Pending POs", accent: "sky", source: "ops", click: { flag: "pending_po" } },
  { id: "awaiting_po", label: "Awaiting PO", accent: "amber", source: "ops", click: { flag: "awaiting_po" } },
  { id: "suppliers", label: "Suppliers", accent: "brand", source: "ops" },
];

export const CHART_STYLES = [
  { id: "bar", label: "Bar" },
  { id: "hbar", label: "Horizontal bar" },
  { id: "pie", label: "Pie" },
  { id: "line", label: "Line" },
];

export const GROUP_METRICS = [
  { id: "total", label: "Total" },
  { id: "open", label: "Open" },
  { id: "placed", label: "Placed" },
  { id: "closed", label: "Closed" },
  { id: "overdue", label: "Overdue" },
  { id: "completion_rate", label: "Completion %" },
];

export const DATASETS = [
  { id: "department", label: "Site", kind: "group", groupKey: "department", filterKey: "department" },
  { id: "assigned_to", label: "Assigned to", kind: "group", groupKey: "assigned_to", filterKey: "assigned_to" },
  { id: "status", label: "Status", kind: "group", groupKey: "status", filterKey: "status" },
  { id: "priority", label: "Priority", kind: "group", groupKey: "priority", filterKey: "priority" },
  { id: "work_type", label: "Purchase type", kind: "group", groupKey: "work_type", filterKey: "work_type" },
  { id: "location", label: "Asset / location", kind: "group", groupKey: "location", filterKey: "location" },
  { id: "supplier", label: "Supplier", kind: "group", groupKey: "supplier", filterKey: "supplier" },
  { id: "issue", label: "Delivery status", kind: "group", groupKey: "issue", filterKey: "delay_reason" },
  { id: "delay_reason", label: "Delay reason", kind: "group", groupKey: "delay_reason", filterKey: "delay_reason" },
  { id: "blockades", label: "Blockades", kind: "dist", dataKey: "blockades", filterKey: "status", extra: { flag: "open" } },
  { id: "aging", label: "Open aging", kind: "dist", dataKey: "aging", filterKey: "aging", valueKey: "id" },
  { id: "reasons", label: "Why still open", kind: "dist", dataKey: "reasons" },
  { id: "delivery", label: "Delivery bars", kind: "dist", dataKey: "delivery", filterKey: "delay_reason" },
  { id: "last_days", label: "Last 14 days", kind: "series", dataKey: "last_days", series: ["created", "done"] },
  { id: "trend", label: "12-month trend", kind: "series", dataKey: "trend", series: ["created", "closed"] },
];

export const MINDMAP_BRANCHES = [
  { id: "sites", label: "Sites", groupKey: "department", filterKey: "department" },
  { id: "status", label: "Status", groupKey: "status", filterKey: "status" },
  { id: "blockades", label: "Blockades", builtin: true },
  { id: "people", label: "Assigned to", groupKey: "assigned_to", filterKey: "assigned_to" },
  { id: "delivery", label: "Delivery", groupKey: "issue", filterKey: "delay_reason" },
  { id: "priority", label: "Priority", groupKey: "priority", filterKey: "priority" },
  { id: "supplier", label: "Supplier", groupKey: "supplier", filterKey: "supplier" },
  { id: "work_type", label: "Purchase type", groupKey: "work_type", filterKey: "work_type" },
  { id: "location", label: "Asset", groupKey: "location", filterKey: "location" },
];

export const CATALOG = [
  { type: "kpis_today", label: "Today numbers", category: "Ready-made", span: "full" },
  { type: "action_queue", label: "Action queue numbers", category: "Ready-made", span: "full" },
  { type: "supplier_kpis", label: "Supplier / PO numbers", category: "Ready-made", span: "full" },
  { type: "kpis_totals", label: "Totals", category: "Ready-made", span: "full" },
  { type: "progress", label: "Progress bar", category: "Ready-made", span: "full" },
  { type: "chart_last_days", label: "Last 14 days", category: "Ready-made", span: "2" },
  { type: "chart_blockades", label: "Blockades pie", category: "Ready-made", span: "1" },
  { type: "chart_trend", label: "12-month trend", category: "Ready-made", span: "2" },
  { type: "chart_status", label: "Status pie", category: "Ready-made", span: "1" },
  { type: "chart_delivery", label: "Delivery bars", category: "Ready-made", span: "1" },
  { type: "chart_aging", label: "Aging bars", category: "Ready-made", span: "1" },
  { type: "chart_reasons", label: "Why still open", category: "Ready-made", span: "1" },
  { type: "table_sites", label: "Site table", category: "Ready-made", span: "1" },
  { type: "table_people", label: "Technician table", category: "Ready-made", span: "1" },
  { type: "table_priority", label: "Priority table", category: "Ready-made", span: "1" },
  { type: "table_types", label: "Purchase type table", category: "Ready-made", span: "1" },
  { type: "table_recent", label: "Latest MRs", category: "Ready-made", span: "full" },
  { type: "mindmap", label: "Full mind map", category: "Ready-made", span: "full" },
  { type: "kpi", label: "Single number", category: "Custom", span: "1", metric: "open" },
  { type: "chart_custom", label: "Custom graph", category: "Custom", span: "1", dataset: "status", style: "bar", metric: "total" },
  { type: "table_custom", label: "Custom table", category: "Custom", span: "1", dataset: "department" },
  { type: "mindmap_custom", label: "Custom mind map", category: "Custom", span: "full", branches: ["sites", "status", "blockades"] },
];

export const DEFAULT_LAYOUT = [
  { id: "progress", type: "progress", span: "full" },
  { id: "kpis_today", type: "kpis_today", span: "full" },
  { id: "action_queue", type: "action_queue", span: "full" },
  { id: "supplier_kpis", type: "supplier_kpis", span: "full" },
  { id: "kpis_totals", type: "kpis_totals", span: "full" },
  { id: "mindmap", type: "mindmap", span: "full" },
  { id: "chart_last_days", type: "chart_last_days", span: "2" },
  { id: "chart_blockades", type: "chart_blockades", span: "1" },
  { id: "chart_trend", type: "chart_trend", span: "2" },
  { id: "chart_status", type: "chart_status", span: "1" },
  { id: "chart_delivery", type: "chart_delivery", span: "1" },
  { id: "chart_aging", type: "chart_aging", span: "1" },
  { id: "chart_reasons", type: "chart_reasons", span: "1" },
  { id: "table_sites", type: "table_sites", span: "1" },
  { id: "table_people", type: "table_people", span: "1" },
  { id: "table_priority", type: "table_priority", span: "1" },
  { id: "table_recent", type: "table_recent", span: "full" },
];

export function loadLayout() {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY);
    if (!raw) return DEFAULT_LAYOUT.map((w) => ({ ...w }));
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed;
  } catch {
    /* ignore */
  }
  return DEFAULT_LAYOUT.map((w) => ({ ...w }));
}

export function saveLayout(widgets) {
  localStorage.setItem(LAYOUT_KEY, JSON.stringify(widgets));
}

export function readDashCache() {
  try {
    const raw = sessionStorage.getItem(DASH_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && parsed.kpis) return parsed;
  } catch {
    /* ignore */
  }
  return null;
}

export function writeDashCache(data) {
  try {
    sessionStorage.setItem(DASH_CACHE_KEY, JSON.stringify(data));
  } catch {
    /* quota */
  }
}

export function clearDashCache() {
  try {
    sessionStorage.removeItem(DASH_CACHE_KEY);
  } catch {
    /* ignore */
  }
}

export function datasetById(id) {
  return DATASETS.find((d) => d.id === id) || DATASETS[2];
}

export function metricValue(data, metricId) {
  const meta = KPI_METRICS.find((m) => m.id === metricId);
  if (!meta) return data?.kpis?.[metricId];
  if (meta.source === "ops") return data?.ops?.[metricId];
  return data?.kpis?.[metricId];
}

export function chartRows(data, datasetId) {
  const ds = datasetById(datasetId);
  if (ds.kind === "group") return data?.groups?.[ds.groupKey] || [];
  if (ds.kind === "dist" || ds.kind === "series") return data?.[ds.dataKey] || [];
  return [];
}

export function buildMindmap(data, branchIds) {
  const ids = branchIds?.length ? branchIds : MINDMAP_BRANCHES.map((b) => b.id);
  const root = data?.mindmap?.root || {
    id: "all",
    label: "All material requests",
    value: data?.kpis?.total || 0,
    filter: {},
  };
  const builtin = Object.fromEntries((data?.mindmap?.branches || []).map((b) => [b.id, b]));
  const branches = ids
    .map((id) => {
      if (builtin[id]) return builtin[id];
      const spec = MINDMAP_BRANCHES.find((b) => b.id === id);
      if (!spec || spec.builtin) return null;
      const rows = (data?.groups?.[spec.groupKey] || []).slice(0, 12);
      return {
        id,
        label: spec.label,
        value: rows.reduce((s, r) => s + (r.total || 0), 0),
        filter: {},
        children: rows.map((r) => ({
          id: `${id}:${r.name}`,
          label: r.name,
          value: r.total,
          open: r.open,
          closed: r.closed,
          filter: { [spec.filterKey]: r.name },
        })),
      };
    })
    .filter(Boolean);
  return { root, branches };
}

export function newWidget(type, extras = {}) {
  const spec = CATALOG.find((c) => c.type === type) || { type, span: "1", label: type };
  const w = { id: `${type}-${Date.now()}`, type, span: spec.span || "1" };
  if (type === "kpi") w.metric = extras.metric || spec.metric || "open";
  if (type === "chart_custom") {
    w.dataset = extras.dataset || spec.dataset || "status";
    w.style = extras.style || spec.style || "bar";
    w.metric = extras.metric || spec.metric || "total";
    w.title = extras.title || "";
  }
  if (type === "table_custom") w.dataset = extras.dataset || spec.dataset || "department";
  if (type === "mindmap_custom") w.branches = extras.branches || spec.branches || ["sites", "status", "blockades"];
  return { ...w, ...extras, id: w.id, type: w.type };
}

export function chartTitle(w) {
  if (w.title) return w.title;
  const ds = datasetById(w.dataset);
  const style = CHART_STYLES.find((s) => s.id === w.style)?.label || "Chart";
  const metric = GROUP_METRICS.find((m) => m.id === w.metric)?.label;
  if (ds.kind === "series") return ds.label;
  if (metric && ds.kind === "group") return `${ds.label} · ${metric}`;
  return `${ds.label} · ${style}`;
}
