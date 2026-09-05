import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { api, getToken, setToken } from "../lib/api.js";

const AuthContext = createContext(null);

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
    } catch {
      setToken(null);
      setUser(null);
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
    return data.user;
  }

  function logout() {
    setToken(null);
    setUser(null);
  }

  const can = (perm) => {
    if (!user) return false;
    if (user.role === "admin") return true;
    const map = {
      admin: ["view", "edit", "create", "delete", "reports", "analytics", "settings", "users", "audit", "backup"],
      manager: ["view", "edit", "create", "reports", "analytics", "audit"],
      user: ["view", "edit", "reports"],
    };
    return (map[user.role] || []).includes(perm);
  };

  const value = useMemo(() => ({ user, loading, login, logout, can }), [user, loading]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
