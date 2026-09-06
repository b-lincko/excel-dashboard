export const LAYOUT_KEY = "woms_dash_layout_v1";
export const DASH_CACHE_KEY = "woms_dash_cache_v1";

export const KPI_METRICS = [
  { id: "created_today", label: "Jobs in today", accent: "brand" },
  { id: "done_today", label: "Jobs done today", accent: "emerald" },
  { id: "delivered_today", label: "Delivered today", accent: "sky" },
  { id: "blockades", label: "Blockades", accent: "rose" },
  { id: "in_progress", label: "In progress", accent: "indigo" },
  { id: "overdue", label: "Overdue", accent: "rose" },
  { id: "total", label: "Total MRs", accent: "brand" },
  { id: "open", label: "Open", accent: "sky" },
  { id: "closed", label: "Closed", accent: "emerald" },
  { id: "pending", label: "Pending / NTP", accent: "amber" },
  { id: "completion_rate", label: "Completion rate", accent: "emerald", suffix: "%" },
  { id: "average_closing_days", label: "Avg close (days)", accent: "brand" },
  { id: "average_aging_days", label: "Avg aging (days)", accent: "amber" },
];

export const CATALOG = [
  { type: "kpis_today", label: "Today numbers", category: "Numbers", span: "full" },
  { type: "kpis_totals", label: "Totals", category: "Numbers", span: "full" },
  { type: "progress", label: "Progress bar", category: "Numbers", span: "full" },
  { type: "kpi", label: "Single number", category: "Numbers", span: "1", metric: "open" },
  { type: "mindmap", label: "Mind map", category: "Mind maps", span: "full" },
  { type: "chart_last_days", label: "Last 14 days", category: "Graphs", span: "2" },
  { type: "chart_blockades", label: "Blockades pie", category: "Graphs", span: "1" },
  { type: "chart_trend", label: "12-month trend", category: "Graphs", span: "2" },
  { type: "chart_status", label: "Status pie", category: "Graphs", span: "1" },
  { type: "chart_delivery", label: "Delivery bars", category: "Graphs", span: "1" },
  { type: "chart_aging", label: "Aging bars", category: "Graphs", span: "1" },
  { type: "chart_reasons", label: "Why still open", category: "Graphs", span: "1" },
  { type: "table_sites", label: "Site table", category: "Tables", span: "1" },
  { type: "table_people", label: "Technician table", category: "Tables", span: "1" },
  { type: "table_priority", label: "Priority table", category: "Tables", span: "1" },
  { type: "table_types", label: "Purchase type table", category: "Tables", span: "1" },
  { type: "table_recent", label: "Latest MRs", category: "Tables", span: "full" },
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

export function newWidget(type) {
  const spec = CATALOG.find((c) => c.type === type) || { type, span: "1", label: type };
  const w = { id: `${type}-${Date.now()}`, type, span: spec.span || "1" };
  if (type === "kpi") w.metric = spec.metric || "open";
  return w;
}
