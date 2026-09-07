import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useAuth } from "./AuthContext.jsx";
import { filterTourSteps, markTourSeen, TOUR_STEPS, tourSeen } from "../lib/tour.js";

const TourContext = createContext(null);

export function TourProvider({ children }) {
  const { user, can, canPage, loading } = useAuth();
  const [index, setIndex] = useState(-1);

  const steps = useMemo(
    () => filterTourSteps(TOUR_STEPS, { can, canPage }),
    // can/canPage are new each render; user identity is the real input
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [user?.username, user?.role, user?.permissions]
  );
  const active = index >= 0 && index < steps.length;
  const step = active ? steps[index] : null;

  const stop = useCallback(
    (mark = true) => {
      if (mark && user?.username) markTourSeen(user.username);
      setIndex(-1);
    },
    [user?.username]
  );

  const start = useCallback(() => {
    setIndex(0);
  }, []);

  const next = useCallback(() => {
    setIndex((i) => {
      if (i < 0) return i;
      if (i >= steps.length - 1) {
        if (user?.username) markTourSeen(user.username);
        return -1;
      }
      return i + 1;
    });
  }, [steps.length, user?.username]);

  const prev = useCallback(() => {
    setIndex((i) => Math.max(0, i - 1));
  }, []);

  useEffect(() => {
    if (loading || !user?.username) {
      setIndex(-1);
      return;
    }
    if (tourSeen(user.username)) return;
    const t = window.setTimeout(() => {
      if (!tourSeen(user.username)) setIndex((i) => (i < 0 ? 0 : i));
    }, 800);
    return () => window.clearTimeout(t);
  }, [loading, user?.username]);

  const value = useMemo(
    () => ({
      active,
      index,
      step,
      steps,
      total: steps.length,
      start,
      stop,
      next,
      prev,
    }),
    [active, index, step, steps, start, stop, next, prev]
  );

  return <TourContext.Provider value={value}>{children}</TourContext.Provider>;
}

export function useTour() {
  const ctx = useContext(TourContext);
  if (!ctx) {
    return {
      active: false,
      index: -1,
      step: null,
      steps: [],
      total: 0,
      start: () => {},
      stop: () => {},
      next: () => {},
      prev: () => {},
    };
  }
  return ctx;
}
