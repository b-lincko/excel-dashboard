import { useEffect, useState } from "react";
import { api } from "./api.js";

/**
 * Tiny stale-while-revalidate cache for the heavy briefing payloads.
 *
 * Tab switches used to refetch /api/ops/* from scratch and the pages flashed
 * "—" + "updating…" for seconds. With this store the page paints the cached
 * payload instantly and revalidates in the background; the backend also keeps
 * its own versioned aggregation cache, so a revalidation is cheap.
 *
 * Any `woms:data` event (a save somewhere) marks entries stale: still painted
 * from cache, but the next fetch actually asks the server again.
 */
const store = new Map(); // key -> { data, at, promise }

let wired = false;
function ensureWired() {
  if (wired || typeof window === "undefined") return;
  wired = true;
  window.addEventListener("woms:data", () => {
    for (const entry of store.values()) entry.at = 0;
  });
}

export function peekCache(key) {
  return store.get(key)?.data ?? null;
}

export function fetchCached(key, url, { ttl = 15000 } = {}) {
  ensureWired();
  const entry = store.get(key) || null;
  if (entry?.promise) return entry.promise; // a revalidation is already running
  if (entry && entry.data && Date.now() - entry.at < ttl) return Promise.resolve(entry.data);
  const promise = api
    .get(url)
    .then((data) => {
      store.set(key, { data, at: Date.now(), promise: null });
      return data;
    })
    .catch((err) => {
      const e = store.get(key);
      if (e) e.promise = null;
      throw err;
    });
  store.set(key, { data: entry?.data ?? null, at: entry?.at ?? 0, promise });
  return promise;
}

/**
 * data lives in the shared store: first visit fetches, later visits (tab
 * switches) paint instantly and revalidate in the background.
 */
export function useApiData(key, url, deps = [], { ttl = 15000 } = {}) {
  const [data, setData] = useState(() => store.get(key)?.data ?? null);
  const [loading, setLoading] = useState(() => !(store.get(key)?.data ?? null));

  useEffect(() => {
    let cancelled = false;
    const cachedData = store.get(key)?.data ?? null;
    if (cachedData) {
      setData(cachedData);
      setLoading(false);
    } else {
      setLoading(true);
    }
    fetchCached(key, url, { ttl })
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, url, ttl, ...deps]);

  return { data, setData, loading };
}

/** Options change rarely — share one cached fetch across pages. */
export function useOptionsCache(ttl = 60000) {
  const [options, setOptions] = useState(() => store.get("wo-options")?.data ?? null);
  useEffect(() => {
    let cancelled = false;
    const hit = store.get("wo-options")?.data;
    if (hit) setOptions(hit);
    fetchCached("wo-options", "/api/work-orders/options", { ttl })
      .then((d) => {
        if (!cancelled) setOptions(d.options || {});
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ttl]);
  return options;
}
