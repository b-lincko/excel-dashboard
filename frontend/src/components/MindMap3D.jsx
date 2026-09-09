import { useEffect, useMemo, useRef, useState } from "react";
import { prefersReducedMotion } from "../lib/webgl.js";

const BRANCH_COLOR = {
  sites: "#0ea5e9",
  status: "#6366f1",
  blockades: "#f43f5e",
  people: "#8b5cf6",
  delivery: "#14b8a6",
  priority: "#f59e0b",
};

function graphFingerprint(root, branches) {
  const parts = [];
  function walk(n) {
    if (!n) return;
    parts.push(`${n.id}:${n.value ?? 0}:${n.open ?? ""}:${n.label || ""}`);
    (n.children || []).forEach(walk);
  }
  walk(root);
  (branches || []).forEach(walk);
  return parts.join("|");
}

function shorten(text, max = 18) {
  const s = String(text || "");
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

function layoutGraph(root, branches) {
  const nodes = [];
  const links = [];
  if (!root) return { nodes, links };
  nodes.push({
    id: root.id,
    label: root.label,
    value: Number(root.value) || 0,
    kind: "root",
    color: "#0d9f8a",
    node: root,
    x: 0,
    y: 0,
    r: 38,
  });
  const list = branches || [];
  const n = Math.max(list.length, 1);
  list.forEach((branch, i) => {
    const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
    const radius = 168;
    const bx = Math.cos(angle) * radius;
    const by = Math.sin(angle) * radius;
    const color = BRANCH_COLOR[branch.id] || "#64748b";
    nodes.push({
      id: branch.id,
      label: branch.label,
      value: Number(branch.value) || 0,
      kind: "branch",
      color,
      node: branch,
      x: bx,
      y: by,
      r: 24,
    });
    links.push({ from: root.id, to: branch.id, color });
    const kids = (branch.children || []).slice(0, 8);
    const span = Math.min(1.15, Math.max(0.28, kids.length * 0.16));
    kids.forEach((child, j) => {
      const t = kids.length === 1 ? 0 : j / (kids.length - 1) - 0.5;
      const ka = angle + t * span;
      const kr = 292;
      const cx = Math.cos(ka) * kr;
      const cy = Math.sin(ka) * kr;
      nodes.push({
        id: child.id,
        label: child.label,
        value: Number(child.value) || 0,
        kind: "leaf",
        color,
        node: child,
        x: cx,
        y: cy,
        r: 13,
        outside: ka,
      });
      links.push({ from: branch.id, to: child.id, color });
    });
  });
  return { nodes, links };
}

function nodeRadius(item) {
  const v = Math.max(0, Number(item.value) || 0);
  const base = item.kind === "root" ? 36 : item.kind === "branch" ? 22 : 12;
  return Math.min(item.kind === "root" ? 46 : 30, base + Math.log1p(v) * (item.kind === "leaf" ? 0.35 : 0.7));
}

function curvePath(a, b) {
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const bump = Math.min(36, len * 0.12);
  const cx = mx + (-dy / len) * bump;
  const cy = my + (dx / len) * bump;
  return `M ${a.x} ${a.y} Q ${cx} ${cy} ${b.x} ${b.y}`;
}

export default function MindMap3D({ root, branches, selectedId, onSelect }) {
  const svgRef = useRef(null);
  const hoverRef = useRef(false);
  const onSelectRef = useRef(onSelect);
  const [hover, setHover] = useState("");
  onSelectRef.current = onSelect;

  const fingerprint = useMemo(() => graphFingerprint(root, branches), [root, branches]);
  const graph = useMemo(() => layoutGraph(root, branches), [fingerprint]); // eslint-disable-line react-hooks/exhaustive-deps
  const byId = useMemo(() => Object.fromEntries(graph.nodes.map((n) => [n.id, n])), [graph]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return undefined;
    const reduced = prefersReducedMotion();
    let running = true;
    let visible = true;
    let raf = 0;
    const t0 = performance.now();
    const io = new IntersectionObserver(
      (entries) => {
        visible = entries.some((e) => e.isIntersecting);
      },
      { threshold: 0.05 }
    );
    io.observe(svg);

    function tick(now) {
      if (!running) return;
      raf = requestAnimationFrame(tick);
      if (!visible) return;
      const t = (now - t0) / 1000;
      const pause = reduced || hoverRef.current;
      svg.querySelectorAll("[data-node]").forEach((el, i) => {
        const x = Number(el.dataset.x);
        const y = Number(el.dataset.y);
        const dx = pause ? 0 : Math.cos(t * 0.7 + i * 0.55) * 3.2;
        const dy = pause ? 0 : Math.sin(t * 1.05 + i * 0.4) * 4.5;
        el.setAttribute("transform", `translate(${x + dx} ${y + dy})`);
      });
      const rootEl = svg.querySelector("[data-kind='root'] circle.mm-core");
      if (rootEl && !reduced) {
        const pulse = pause ? 1 : 1 + Math.sin(t * 1.6) * 0.045;
        rootEl.setAttribute("transform", `scale(${pulse})`);
      }
    }
    raf = requestAnimationFrame(tick);
    return () => {
      running = false;
      cancelAnimationFrame(raf);
      io.disconnect();
    };
  }, [fingerprint]);

  if (!root) return null;

  const vb = { x: -500, y: -340, w: 1000, h: 680 };

  return (
    <div className="relative min-h-[380px] h-[min(52vh,520px)] bg-gradient-to-b from-slate-50 to-white dark:from-ink-900 dark:to-ink-800">
      <svg
        ref={svgRef}
        viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
        className={`absolute inset-0 w-full h-full ${hover ? "mm-paused" : ""}`}
        role="img"
        aria-label="2D mind map of live material-request counts"
      >
        <defs>
          <filter id="mm-soft" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="6" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {graph.links.map((link) => {
          const a = byId[link.from];
          const b = byId[link.to];
          if (!a || !b) return null;
          return (
            <path
              key={`${link.from}-${link.to}`}
              d={curvePath(a, b)}
              fill="none"
              stroke={link.color}
              strokeWidth={link.from === root.id ? 2.4 : 1.5}
              strokeOpacity="0.38"
              className="mm-link"
            />
          );
        })}
        {graph.nodes.map((item) => {
          const r = nodeRadius(item);
          const selected = item.id === selectedId;
          const caption = `${shorten(item.label, item.kind === "leaf" ? 14 : 20)} · ${item.value}`;
          const labelY = item.kind === "root" ? r + 18 : item.kind === "branch" ? r + 16 : r + 14;
          return (
            <g
              key={item.id}
              data-node
              data-kind={item.kind}
              data-x={item.x}
              data-y={item.y}
              transform={`translate(${item.x} ${item.y})`}
              className="cursor-pointer"
              onMouseEnter={() => {
                hoverRef.current = true;
                setHover(`${item.label} · ${item.value}`);
              }}
              onMouseLeave={() => {
                hoverRef.current = false;
                setHover("");
              }}
              onClick={() => onSelectRef.current?.(item.node)}
            >
              {item.kind === "root" && (
                <circle r={r + 16} fill={item.color} opacity="0.12" className="mm-halo" />
              )}
              {selected && (
                <circle r={r + 7} fill="none" stroke={item.color} strokeWidth="2.5" strokeOpacity="0.85" />
              )}
              <circle
                className="mm-core"
                r={r}
                fill={item.color}
                filter={item.kind === "root" ? "url(#mm-soft)" : undefined}
                stroke={selected ? "#fff" : "rgba(255,255,255,0.55)"}
                strokeWidth={selected ? 3 : 1.25}
              />
              {item.kind !== "leaf" && (
                <text
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill="#fff"
                  fontSize={item.kind === "root" ? 13 : 10}
                  fontWeight="700"
                  className="pointer-events-none select-none"
                >
                  {item.value}
                </text>
              )}
              <text
                textAnchor="middle"
                y={labelY}
                fill="currentColor"
                className="pointer-events-none select-none fill-slate-700 dark:fill-slate-200"
                fontSize={item.kind === "leaf" ? 10 : 11}
                fontWeight="600"
              >
                {caption}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="absolute left-3 bottom-3 right-3 flex items-end justify-between gap-3 pointer-events-none">
        <div className="rounded-full bg-white/85 dark:bg-ink-900/80 px-2.5 py-1 text-[11px] text-slate-500 shadow-sm">
          2D map · click a node · counts are live
        </div>
        {hover ? (
          <div className="rounded-full bg-brand-700 text-white px-2.5 py-1 text-[11px] font-semibold shadow-sm">{hover}</div>
        ) : null}
      </div>
    </div>
  );
}
