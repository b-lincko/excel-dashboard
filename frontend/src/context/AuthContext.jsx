import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { api, getToken, setToken } from "../lib/api.js";

const AuthContext = createContext(null);

const ROLE_PERMS = {
  admin: ["view", "edit", "create", "delete", "reports", "analytics", "settings", "users", "audit", "backup"],
  manager: ["view", "edit", "create", "reports", "analytics", "audit"],
  user: ["view", "edit", "reports"],
  readonly: ["view", "reports", "analytics"],
  guest: ["view"],
};

export const GUEST_PAGES = ["dashboard", "work_orders", "open", "placed", "overdue", "closed", "queue", "suppliers", "analytics", "reports"];

const PAGE_PATHS = {
  dashboard: "/",
  work_orders: "/work-orders",
  open: "/open",
  placed: "/placed",
  overdue: "/overdue",
  closed: "/closed",
  queue: "/queue",
  suppliers: "/suppliers",
  analytics: "/analytics",
  reports: "/reports",
};

export function firstPath(user) {
  if (!user) return "/login";
  if (user.role !== "guest") return "/";
  const pages = user.permissions || [];
  for (const key of GUEST_PAGES) {
    if (pages.includes(key) && PAGE_PATHS[key]) return PAGE_PATHS[key];
  }
  return "/account";
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  async function loadMe() {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.get("/api/auth/me");
      setUser(me);
    } catch (e) {
      if (!e?.offline) {
        setToken(null);
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMe();
    const onUnauth = () => {
      setUser(null);
      setToken(null);
    };
    window.addEventListener("woms:unauthorized", onUnauth);
    return () => window.removeEventListener("woms:unauthorized", onUnauth);
  }, []);

  async function login(username, password) {
    const data = await api.post("/api/auth/login", { username, password });
    setToken(data.access_token);
    setUser(data.user);
    sessionStorage.removeItem("woms_auth_reason");
    return data.user;
  }

  async function logout() {
    try {
      if (getToken()) await api.post("/api/auth/logout");
    } catch {
      /* token may already be invalid */
    }
    setToken(null);
    setUser(null);
  }

  const perms = user?.permissions || ROLE_PERMS[user?.role] || [];

  const can = (perm) => {
    if (!user) return false;
    if (user.role === "admin") return true;
    return perms.includes(perm);
  };

  const canPage = (page) => {
    if (!user) return false;
    if (user.role === "admin") return true;
    if (user.role === "guest") return !page || can(page);
    if (["analytics", "reports", "audit", "users", "settings"].includes(page)) return can(page);
    return can("view");
  };

  const value = useMemo(
    () => ({ user, loading, login, logout, can, canPage, firstPath, GUEST_PAGES }),
    [user, loading]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
