import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext.jsx";
import { filterTourSteps, TOUR_DECKS, tourSeen } from "../lib/tour.js";

const TourContext = createContext(null);

export function TourProvider({ children }) {
  const { user, can, canPage, loading } = useAuth();
  const loc = useLocation();
  const [deck, setDeck] = useState("main");
  const [index, setIndex] = useState(-1);
  const signingTried = useRef(false);

  const steps = useMemo(() => {
    const def = TOUR_DECKS[deck] || TOUR_DECKS.main;
    return filterTourSteps(def.steps, { can, canPage });
    // can/canPage are new each render; user identity is the real input
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deck, user?.username, user?.role, user?.permissions]);

  const active = index >= 0 && index < steps.length;
  const step = active ? steps[index] : null;

  const stop = useCallback(
    (mark = true) => {
      if (mark && user?.username) {
        const def = TOUR_DECKS[deck] || TOUR_DECKS.main;
        def.markSeen(user.username);
      }
      setIndex(-1);
    },
    [deck, user?.username]
  );

  const start = useCallback(() => {
    setDeck("main");
    setIndex(0);
  }, []);

  const startSigning = useCallback(() => {
    setDeck("signing");
    setIndex(0);
  }, []);

  const startDeck = useCallback((name) => {
    if (name === "signing") startSigning();
    else start();
  }, [start, startSigning]);

  const next = useCallback(() => {
    setIndex((i) => {
      if (i < 0) return i;
      if (i >= steps.length - 1) {
        if (user?.username) {
          const def = TOUR_DECKS[deck] || TOUR_DECKS.main;
          def.markSeen(user.username);
        }
        return -1;
      }
      return i + 1;
    });
  }, [deck, steps.length, user?.username]);

  const prev = useCallback(() => {
    setIndex((i) => Math.max(0, i - 1));
  }, []);

  // First-run auto-start of the main tour (~800ms), re-checked so Skip does not restart.
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

  // Signing tour: offer it once, the first time someone who can sign opens the approvals desk.
  useEffect(() => {
    if (loading || !user?.username) return;
    if (signingTried.current) return;
    if (loc.pathname !== "/approvals") return;
    signingTried.current = true;
    if (index >= 0) return; // a tour is already running
    const def = TOUR_DECKS.signing;
    const eligible = filterTourSteps(def.steps, { can, canPage }).length > 0;
    if (!eligible) return;
    if (def.seen(user.username)) return;
    const t = window.setTimeout(() => {
      if (def.seen(user.username)) return;
      setDeck("signing");
      setIndex((i) => (i < 0 ? 0 : i));
    }, 700);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, user?.username, loc.pathname]);

  const value = useMemo(
    () => ({
      active,
      index,
      step,
      steps,
      total: steps.length,
      deck,
      start,
      startSigning,
      startDeck,
      stop,
      next,
      prev,
    }),
    [active, index, step, steps, deck, start, startSigning, startDeck, stop, next, prev]
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
      deck: "main",
      start: () => {},
      startSigning: () => {},
      startDeck: () => {},
      stop: () => {},
      next: () => {},
      prev: () => {},
    };
  }
  return ctx;
}
