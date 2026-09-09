import { useEffect, useRef, useState } from "react";

function prefersReducedMotion() {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

export default function SignaturePad({ value, onChange, disabled }) {
  const canvasRef = useRef(null);
  const drawing = useRef(false);
  const last = useRef(null);
  const lastMid = useRef(null);
  const width = useRef(2.6);
  const [touched, setTouched] = useState(Boolean(value));
  const [justSaved, setJustSaved] = useState(false);
  const savedTimer = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const ratio = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || 360;
    const h = canvas.clientHeight || 120;
    canvas.width = w * ratio;
    canvas.height = h * ratio;
    ctx.scale(ratio, ratio);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#0f172a";
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, w, h);
    if (value) {
      const img = new Image();
      img.onload = () => ctx.drawImage(img, 0, 0, w, h);
      img.src = value;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function paint(p) {
    const ctx = canvasRef.current.getContext("2d");
    ctx.strokeStyle = "#0f172a";
    ctx.fillStyle = "#0f172a";
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    if (!last.current) {
      // First touch: a small dot, like a pen landing on paper.
      ctx.beginPath();
      ctx.arc(p.x, p.y, width.current / 2, 0, Math.PI * 2);
      ctx.fill();
      last.current = p;
      lastMid.current = p;
      return;
    }
    // Speed → width: slower strokes render thicker, like real ink.
    const d = Math.hypot(p.x - last.current.x, p.y - last.current.y);
    const target = Math.max(1.4, 3.1 - Math.min(d, 24) * 0.07);
    width.current = width.current * 0.65 + target * 0.35; // lerp so the line tapers, never jumps
    ctx.lineWidth = width.current;
    // Quadratic midpoint smoothing: curve through the middle of each segment.
    const mid = { x: (last.current.x + p.x) / 2, y: (last.current.y + p.y) / 2 };
    ctx.beginPath();
    ctx.moveTo(lastMid.current.x, lastMid.current.y);
    ctx.quadraticCurveTo(last.current.x, last.current.y, mid.x, mid.y);
    ctx.stroke();
    lastMid.current = mid;
    last.current = p;
  }

  function pos(e) {
    const canvas = canvasRef.current;
    const r = canvas.getBoundingClientRect();
    const src = e.touches ? e.touches[0] : e;
    return { x: src.clientX - r.left, y: src.clientY - r.top };
  }

  function start(e) {
    if (disabled) return;
    drawing.current = true;
    last.current = null;
    lastMid.current = null;
    width.current = 2.6;
    setTouched(true);
    paint(pos(e));
  }

  function move(e) {
    if (!drawing.current || disabled) return;
    e.preventDefault();
    paint(pos(e));
  }

  function end() {
    if (!drawing.current) return;
    drawing.current = false;
    onChange?.(canvasRef.current.toDataURL("image/png"));
    setJustSaved(true);
    window.clearTimeout(savedTimer.current);
    savedTimer.current = window.setTimeout(() => setJustSaved(false), 1800);
  }

  function clear() {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.clientWidth, canvas.clientHeight);
    last.current = null;
    lastMid.current = null;
    width.current = 2.6;
    setTouched(false);
    setJustSaved(false);
    onChange?.("");
  }

  const showDemo = !disabled && !touched && !value;

  return (
    <div className="sig-pad-wrap">
      <canvas
        ref={canvasRef}
        className="w-full h-40 rounded-lg border border-slate-200 bg-white touch-none dark:border-white/10"
        onMouseDown={start}
        onMouseMove={move}
        onMouseUp={end}
        onMouseLeave={end}
        onTouchStart={start}
        onTouchMove={move}
        onTouchEnd={end}
        data-tour="sign-pad"
      />
      {showDemo && (
        <div className="sig-demo" aria-hidden="true">
          <svg viewBox="0 0 340 90" className="w-full h-24">
            <path
              d="M20 62 C 45 12, 62 12, 58 44 C 55 66, 78 70, 92 40 C 104 15, 116 20, 112 44 C 109 62, 126 66, 142 46 C 158 26, 172 30, 168 50 C 165 66, 186 66, 204 42 C 222 18, 238 24, 236 44 C 234 62, 254 62, 272 44 C 286 30, 300 34, 318 28"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinecap="round"
              pathLength="1"
            />
          </svg>
        </div>
      )}
      {showDemo && (
        <div className="absolute inset-x-0 bottom-3 text-center text-xs pointer-events-none sig-demo-label text-slate-400" aria-hidden="true">
          Draw your signature here with mouse or finger
        </div>
      )}
      {!disabled && (
        <div className="flex items-center gap-2 mt-1">
          <button type="button" className="btn-ghost !px-2 !py-1 text-xs" onClick={clear}>
            Clear signature
          </button>
          {justSaved && !prefersReducedMotion() && (
            <span className="sig-saved inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M2.5 8.5l3.5 3.5 7-8" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Signature captured
            </span>
          )}
        </div>
      )}
    </div>
  );
}
