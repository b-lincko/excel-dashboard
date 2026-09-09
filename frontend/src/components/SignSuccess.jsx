import { useEffect, useState } from "react";

/**
 * Full-screen "signed" moment: an ink flourish draws itself, then a stamp
 * thumps in. Auto-dismisses; click or any key skips. Respects reduced motion
 * via CSS (animations collapse to a static stamp).
 */
export default function SignSuccess({ title = "Signed & locked", note, onDone, duration = 2400 }) {
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    let alive = true;
    const t1 = window.setTimeout(() => alive && setLeaving(true), duration);
    const t2 = window.setTimeout(() => alive && onDone?.(), duration + 380);
    return () => {
      alive = false;
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [duration, onDone]);

  useEffect(() => {
    function skip() {
      setLeaving(true);
    }
    window.addEventListener("keydown", skip);
    return () => window.removeEventListener("keydown", skip);
  }, []);

  return (
    <div
      className={`sign-overlay ${leaving ? "is-leaving" : ""}`}
      role="status"
      aria-live="polite"
      onClick={() => setLeaving(true)}
    >
      <div className="sign-stamp text-center">
        <svg className="sign-flourish w-72 h-28 mx-auto" viewBox="0 0 320 110" fill="none" aria-hidden="true">
          <path
            d="M16 84 C 44 18, 70 14, 66 50 C 62 78, 90 84, 108 48 C 122 20, 136 26, 132 52 C 129 74, 148 80, 168 56 C 188 32, 202 38, 198 60 C 195 78, 216 78, 236 52 C 254 28, 272 34, 270 54 C 268 72, 290 70, 306 58"
            stroke="#34d399"
            strokeWidth="4"
            strokeLinecap="round"
            pathLength="1"
          />
          <path
            d="M210 34 C 226 22, 252 20, 262 30"
            stroke="#34d399"
            strokeWidth="2.4"
            strokeLinecap="round"
            opacity="0.6"
            pathLength="1"
          />
        </svg>
        <div className="sign-stamp-badge mt-2 inline-block rounded-xl border-4 border-emerald-500/80 px-6 py-3 text-emerald-500 dark:text-emerald-300 bg-white/60 dark:bg-emerald-500/10">
          <div className="text-xl font-black uppercase tracking-[0.18em] leading-none">{title}</div>
          {note ? <div className="text-xs font-semibold mt-1.5 text-emerald-700 dark:text-emerald-300/80">{note}</div> : null}
        </div>
      </div>
    </div>
  );
}
