import { useEffect } from "react";
import { BellRing, FileText, MessageCircle, PenLine, Stamp, UserRound, X } from "lucide-react";

/**
 * On-screen popup notifications for new inbox items (the 8s poll in Layout
 * feeds them). Managers get a prominent "Document to sign" card when a
 * purchase slip lands in their signature queue.
 */

const KIND_META = {
  po: { icon: Stamp, title: "Document to sign", tone: "brand", cta: "Review & sign" },
  ping: { icon: BellRing, title: "Follow-up", tone: "amber", cta: "Open slip" },
  accounts: { icon: FileText, title: "Signed slip", tone: "brand", cta: "Open" },
  assign: { icon: UserRound, title: "Assigned to you", tone: "slate", cta: "Open" },
  mention: { icon: PenLine, title: "You were mentioned", tone: "slate", cta: "Open" },
  message: { icon: MessageCircle, title: "New message", tone: "slate", cta: "Open chat" },
  watch: { icon: BellRing, title: "MR updated", tone: "slate", cta: "Open" },
};

const TONES = {
  brand:
    "border-brand-600/40 bg-brand-50/95 dark:bg-brand-900/30 dark:border-brand-500/40",
  amber:
    "border-amber-300 bg-amber-50/95 dark:bg-amber-500/10 dark:border-amber-500/40",
  slate:
    "border-slate-200 bg-white/95 dark:bg-ink-800 dark:border-white/10",
};

export default function NotifyPopups({ items, onOpen, onDismiss }) {
  useEffect(() => {
    if (!items.length) return undefined;
    const timers = items.map((n) => window.setTimeout(() => onDismiss(n.id), 15000));
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [items, onDismiss]);

  if (!items.length) return null;
  return (
    <div className="fixed top-4 right-4 z-[85] w-[min(360px,calc(100vw-2rem))] space-y-2">
      {items.slice(-4).map((n) => {
        const meta = KIND_META[n.kind] || KIND_META.watch;
        const Icon = meta.icon;
        return (
          <div
            key={n.id}
            role="alert"
            className={`toast-in pointer-events-auto rounded-xl border shadow-lg p-3.5 ${TONES[meta.tone] || TONES.slate}`}
          >
            <div className="flex items-start gap-3">
              <span
                className={`mt-0.5 grid place-items-center h-8 w-8 rounded-lg shrink-0 ${
                  meta.tone === "brand"
                    ? "bg-brand-700 text-white"
                    : meta.tone === "amber"
                      ? "bg-amber-500 text-white"
                      : "bg-slate-200 text-slate-600 dark:bg-white/10 dark:text-slate-200"
                }`}
              >
                <Icon size={16} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold leading-tight">{meta.title}</div>
                <div className="text-sm text-slate-600 dark:text-slate-300 mt-0.5 line-clamp-3">{n.body}</div>
                <div className="flex items-center gap-3 mt-2">
                  <button
                    type="button"
                    className="text-sm font-semibold text-brand-700 dark:text-cyan-300 hover:underline"
                    onClick={() => onOpen(n)}
                  >
                    {meta.cta}
                  </button>
                  <span className="text-[11px] text-slate-400">{n.created_at}</span>
                </div>
              </div>
              <button
                type="button"
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-0.5"
                aria-label="Dismiss notification"
                onClick={() => onDismiss(n.id)}
              >
                <X size={14} />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
