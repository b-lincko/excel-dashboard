import { useEffect, useState } from "react";

/** Increments whenever Excel data changes so pages can refresh in place. */
export function useLiveReload() {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const onData = () => setTick((n) => n + 1);
    window.addEventListener("woms:data", onData);
    return () => window.removeEventListener("woms:data", onData);
  }, []);
  return tick;
}

export function goSearch(nav, params) {
  const sp = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    sp.set(k, Array.isArray(v) ? v.join(",") : String(v));
  });
  const s = sp.toString();
  nav(s ? `/work-orders?${s}` : "/work-orders");
}
