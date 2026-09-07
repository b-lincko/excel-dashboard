import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { useTour } from "../context/TourContext.jsx";

function measureTarget(target) {
  if (!target) return null;
  const nodes = [...document.querySelectorAll(`[data-tour="${target}"]`)];
  const el = nodes.find((n) => {
    const r = n.getBoundingClientRect();
    return r.width > 2 && r.height > 2;
  });
  if (!el) return null;
  el.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
  const r = el.getBoundingClientRect();
  if (r.width < 2 && r.height < 2) return null;
  return {
    top: Math.max(8, r.top - 8),
    left: Math.max(8, r.left - 8),
    width: Math.min(window.innerWidth - 16, r.width + 16),
    height: Math.min(window.innerHeight - 16, r.height + 16),
  };
}

function placeCard(hole, card, vw, vh) {
  const pad = 16;
  const w = card?.width || 380;
  const h = card?.height || 220;
  if (!hole) {
    return { top: Math.max(pad, (vh - h) / 2), left: Math.max(pad, (vw - w) / 2) };
  }
  const below = hole.top + hole.height + pad;
  const above = hole.top - h - pad;
  let top = below + h + pad < vh ? below : above > pad ? above : Math.max(pad, vh - h - pad);
  let left = hole.left;
  if (left + w > vw - pad) left = vw - w - pad;
  if (left < pad) left = pad;
  return { top, left };
}

export default function Tour() {
  const { active, step, index, total, next, prev, stop } = useTour();
  const nav = useNavigate();
  const loc = useLocation();
  const cardRef = useRef(null);
  const [hole, setHole] = useState(null);
  const [cardPos, setCardPos] = useState({ top: 80, left: 24 });

  useEffect(() => {
    if (!active || !step) return;
    const want = step.path || "/";
    if (loc.pathname !== want) nav(want);
  }, [active, step?.id, step?.path, loc.pathname, nav]);

  useLayoutEffect(() => {
    if (!active || !step) {
      setHole(null);
      return;
    }
    let tries = 0;
    let timer;
    function tick() {
      const nextHole = measureTarget(step.target);
      setHole(nextHole);
      tries += 1;
      if (!nextHole && step.target && tries < 24) {
        timer = window.setTimeout(tick, 60);
      }
    }
    tick();
    function onWin() {
      setHole(measureTarget(step.target));
    }
    window.addEventListener("resize", onWin);
    window.addEventListener("scroll", onWin, true);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("resize", onWin);
      window.removeEventListener("scroll", onWin, true);
    };
  }, [active, step?.id, step?.target, loc.pathname]);

  useLayoutEffect(() => {
    if (!active) return;
    const card = cardRef.current?.getBoundingClientRect();
    setCardPos(placeCard(hole, card, window.innerWidth, window.innerHeight));
  }, [active, hole, step?.id, step?.body]);

  useEffect(() => {
    if (!active) return;
    function onKey(e) {
      if (e.key === "Escape") {
        e.preventDefault();
        stop(true);
      } else if (e.key === "ArrowRight" || e.key === "Enter") {
        e.preventDefault();
        next();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        prev();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, next, prev, stop]);

  if (!active || !step) return null;

  const last = index >= total - 1;

  return createPortal(
    <div className="tour-root" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      <div className="tour-dim" style={hole ? { background: "transparent" } : undefined} />
      {hole && (
        <div
          className="tour-hole"
          style={{ top: hole.top, left: hole.left, width: hole.width, height: hole.height }}
        />
      )}
      <div
        ref={cardRef}
        className="tour-card"
        style={{ top: cardPos.top, left: cardPos.left }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 mb-2">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-cyan-700 dark:text-cyan-300">
            {index + 1} / {total}
          </div>
          <button type="button" className="text-xs text-slate-500 hover:underline" onClick={() => stop(true)}>
            Skip tour
          </button>
        </div>
        <div className="h-1 rounded-full bg-slate-100 dark:bg-white/10 mb-3 overflow-hidden">
          <div className="h-full bg-brand-700 transition-all" style={{ width: `${((index + 1) / total) * 100}%` }} />
        </div>
        <h2 id="tour-title" className="text-lg font-bold tracking-tight">
          {step.title}
        </h2>
        <p className="text-sm text-slate-600 dark:text-slate-300 mt-2 leading-relaxed">{step.body}</p>
        <div className="flex items-center justify-between gap-2 mt-5">
          <button type="button" className="btn-outline" onClick={prev} disabled={index === 0}>
            Back
          </button>
          <button type="button" className="btn-primary" onClick={next} autoFocus>
            {last ? "Finish" : "Next"}
          </button>
        </div>
        <p className="text-[11px] text-slate-400 mt-3">Enter or → next · ← back · Esc skip</p>
      </div>
    </div>,
    document.body
  );
}
