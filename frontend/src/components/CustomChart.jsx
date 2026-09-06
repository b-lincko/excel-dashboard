import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import ChartCard from "./ChartCard.jsx";
import { chartRows, chartTitle, datasetById } from "../lib/widgets.js";

const PIE = ["#0F3D5E", "#1D6A96", "#0EA5E9", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#64748B", "#14B8A6"];
const SERIES_COLORS = { created: "#0F3D5E", done: "#10B981", closed: "#10B981", open: "#F59E0B", overdue: "#EF4444" };

export default function CustomChart({ widget, data, go }) {
  const ds = datasetById(widget.dataset);
  const style = widget.style || (ds.kind === "series" ? "line" : "bar");
  const metric = widget.metric || "total";
  const raw = chartRows(data, widget.dataset) || [];
  const rows = raw.slice(0, 16).map((r) => ({
    ...r,
    name: r.name || r.label || r.date || "",
    plot: Number(r[metric] ?? r.value ?? 0) || 0,
  }));
  const title = chartTitle(widget);

  function onSlice(d) {
    if (!d?.name && d?.id == null) return;
    if (ds.valueKey === "id" && d.id) {
      go({ flag: "open", aging: d.id });
      return;
    }
    if (ds.filterKey) go({ ...(ds.extra || {}), [ds.filterKey]: d.name });
  }

  const chart = (() => {
    if (ds.kind === "series") {
      const keys = ds.series || ["created", "closed"];
      if (style === "line") {
        return (
          <LineChart data={rows}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Legend />
            {keys.map((k) => (
              <Line key={k} type="monotone" dataKey={k} stroke={SERIES_COLORS[k] || "#0F3D5E"} strokeWidth={2} dot={false} isAnimationActive={false} />
            ))}
          </LineChart>
        );
      }
      return (
        <BarChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} />
          <YAxis allowDecimals={false} />
          <Tooltip />
          <Legend />
          {keys.map((k) => (
            <Bar key={k} dataKey={k} fill={SERIES_COLORS[k] || "#0F3D5E"} radius={[4, 4, 0, 0]} isAnimationActive={false} />
          ))}
        </BarChart>
      );
    }
    if (style === "pie") {
      return (
        <PieChart>
          <Pie data={rows} dataKey="plot" nameKey="name" innerRadius={48} outerRadius={78} isAnimationActive={false} onClick={onSlice}>
            {rows.map((_, i) => (
              <Cell key={i} fill={PIE[i % PIE.length]} />
            ))}
          </Pie>
          <Tooltip />
          <Legend />
        </PieChart>
      );
    }
    if (style === "hbar") {
      return (
        <BarChart data={rows} layout="vertical" margin={{ left: 24 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis type="number" allowDecimals={false} />
          <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="plot" name={metric} fill="#1D6A96" radius={[0, 6, 6, 0]} isAnimationActive={false} onClick={onSlice} />
        </BarChart>
      );
    }
    if (style === "line") {
      return (
        <LineChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} />
          <YAxis allowDecimals={false} />
          <Tooltip />
          <Line type="monotone" dataKey="plot" name={metric} stroke="#0F3D5E" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      );
    }
    return (
      <BarChart data={rows}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={rows.length > 6 ? -25 : 0} textAnchor={rows.length > 6 ? "end" : "middle"} height={rows.length > 6 ? 48 : 30} />
        <YAxis allowDecimals={false} />
        <Tooltip />
        <Bar dataKey="plot" name={metric} fill="#0EA5E9" radius={[6, 6, 0, 0]} isAnimationActive={false} onClick={onSlice} />
      </BarChart>
    );
  })();

  return (
    <ChartCard title={title} subtitle="Click a slice or bar to open matching Excel rows">
      <ResponsiveContainer width="100%" height="100%">
        {chart}
      </ResponsiveContainer>
    </ChartCard>
  );
}
