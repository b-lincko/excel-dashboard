import { createContext, useCallback, useContext, useMemo, useState } from "react";

const UiContext = createContext(null);

export function UiProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const [dialog, setDialog] = useState(null);

  const toast = useCallback((message, tone = "info") => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setToasts((list) => [...list.slice(-4), { id, message, tone }]);
    window.setTimeout(() => {
      setToasts((list) => list.filter((t) => t.id !== id));
    }, 4200);
  }, []);

  const ask = useCallback((opts) => {
    return new Promise((resolve) => {
      setDialog({
        title: opts.title || "Please confirm",
        body: opts.body || "",
        confirmLabel: opts.confirmLabel || "Confirm",
        danger: !!opts.danger,
        resolve,
      });
    });
  }, []);

  const value = useMemo(() => ({ toast, ask }), [toast, ask]);

  return (
    <UiContext.Provider value={value}>
      {children}
      <div className="fixed z-[70] bottom-4 right-4 space-y-2 w-[min(360px,calc(100vw-2rem))] pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`pointer-events-auto rounded-xl px-4 py-3 text-sm shadow-lg border ${
              t.tone === "error"
                ? "bg-rose-50 text-rose-800 border-rose-200 dark:bg-rose-500/15 dark:text-rose-100 dark:border-rose-500/30"
                : t.tone === "success"
                  ? "bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-100 dark:border-emerald-500/30"
                  : "bg-white text-slate-800 border-slate-200 dark:bg-ink-800 dark:text-slate-100 dark:border-white/10"
            }`}
          >
            {t.message}
          </div>
        ))}
      </div>
      {dialog && (
        <div className="fixed inset-0 z-[80] grid place-items-center p-4">
          <button
            className="absolute inset-0 bg-black/50"
            aria-label="Cancel"
            onClick={() => {
              dialog.resolve(false);
              setDialog(null);
            }}
          />
          <div role="dialog" aria-modal="true" className="relative card p-6 w-full max-w-md">
            <div className="text-lg font-semibold">{dialog.title}</div>
            {dialog.body && <p className="text-sm text-slate-500 mt-2 whitespace-pre-wrap">{dialog.body}</p>}
            <div className="flex justify-end gap-2 mt-5">
              <button
                className="btn-outline"
                onClick={() => {
                  dialog.resolve(false);
                  setDialog(null);
                }}
              >
                Cancel
              </button>
              <button
                className={dialog.danger ? "btn-danger" : "btn-primary"}
                autoFocus
                onClick={() => {
                  dialog.resolve(true);
                  setDialog(null);
                }}
              >
                {dialog.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </UiContext.Provider>
  );
}

export function useUi() {
  const ctx = useContext(UiContext);
  if (!ctx) {
    return {
      toast: () => {},
      ask: async () => true,
    };
  }
  return ctx;
}
