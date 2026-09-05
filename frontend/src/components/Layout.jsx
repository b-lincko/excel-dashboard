import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  ClipboardList,
  FileText,
  FolderOpen,
  LayoutDashboard,
  LogOut,
  Moon,
  Search,
  Settings,
  Shield,
  Sun,
  Users,
  CheckCircle2,
  RefreshCw,
} from "lucide-react";
import { useAuth } from "../context/AuthContext.jsx";
import { useTheme } from "../context/ThemeContext.jsx";
import { api } from "../lib/api.js";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/work-orders", label: "Work Orders", icon: ClipboardList },
  { to: "/open", label: "Open Orders", icon: FolderOpen },
  { to: "/overdue", label: "Overdue", icon: AlertTriangle },
  { to: "/closed", label: "Closed Orders", icon: CheckCircle2 },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/reports", label: "Reports", icon: FileText },
  { to: "/audit", label: "Audit Log", icon: Shield, perm: "audit" },
  { to: "/users", label: "Users", icon: Users, perm: "users" },
  { to: "/settings", label: "Settings", icon: Settings, perm: "settings" },
];

export default function Layout() {
  const { user, logout, can } = useAuth();
  const { theme, toggle } = useTheme();
  const nav = useNavigate();
  const loc = useLocation();
  const [sync, setSync] = useState(null);
  const [q, setQ] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [intervalSec, setIntervalSec] = useState(10);

  async function loadSync() {
    try {
      const next = await api.get("/api/sync/status");
      setSync((prev) => {
        if (prev && next.sync_token && prev.sync_token !== next.sync_token) {
          window.dispatchEvent(new CustomEvent("woms:data", { detail: next }));
        }
        return next;
      });
    } catch (e) {
      setSync({
        synchronized: false,
        error: e.offline ? e.message : "Excel file is currently unavailable.",
        offline: !!e.offline,
      });
    }
  }

  useEffect(() => {
    loadSync();
    if (!intervalSec) return undefined;
    const id = setInterval(loadSync, intervalSec * 1000);
    return () => clearInterval(id);
  }, [loc.pathname, intervalSec]);

  async function refresh() {
    setRefreshing(true);
    try {
      const next = await api.post("/api/sync/refresh");
      setSync(next);
      window.dispatchEvent(new CustomEvent("woms:data", { detail: next }));
    } catch (e) {
      setSync({ synchronized: false, error: e.message });
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div className="min-h-screen flex bg-slate-50 dark:bg-ink-900">
      <aside className="w-[250px] shrink-0 bg-ink-900 text-slate-200 flex flex-col border-r border-white/5">
        <div className="px-5 py-5 flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-cyan-400 to-brand-700 grid place-items-center font-extrabold text-white shadow-lg">
            WO
          </div>
          <div>
            <div className="font-bold tracking-tight text-white leading-tight">Linkco MR</div>
            <div className="text-[11px] text-slate-400">IM Work Order · Material Request</div>
          </div>
        </div>
        <nav className="px-3 flex-1 space-y-0.5">
          {NAV.filter((n) => !n.perm || can(n.perm)).map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition ${
                  isActive
                    ? "bg-white/10 text-white"
                    : "text-slate-400 hover:text-white hover:bg-white/5"
                }`
              }
            >
              <n.icon size={16} />
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-white/5">
          <div className="text-xs text-slate-400 mb-1">{user?.full_name}</div>
          <div className="flex items-center justify-between">
            <span className="text-[11px] uppercase tracking-wider text-cyan-300/80">{user?.role}</span>
            <button className="btn-ghost !text-slate-400 !px-2 !py-1" onClick={logout} title="Sign out">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-16 shrink-0 bg-white/80 dark:bg-ink-800/80 backdrop-blur border-b border-slate-200 dark:border-white/5 flex items-center gap-4 px-6">
          <form
            className="flex-1 max-w-xl relative"
            onSubmit={(e) => {
              e.preventDefault();
              nav(`/work-orders?q=${encodeURIComponent(q)}`);
            }}
          >
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search work orders, technicians, issues, remarks…"
              className="pl-9"
            />
          </form>
          <div className="flex items-center gap-2 text-xs">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-medium ${
                sync?.synchronized
                  ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
                  : "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300"
              }`}
              title={sync?.error || sync?.path}
            >
              <Activity size={12} />
              {sync?.synchronized ? "Synchronized" : sync?.error ? "Excel unavailable" : "Checking…"}
            </span>
            {sync?.mtime && (
              <span className="hidden lg:inline text-slate-400">Last Excel sync {sync.mtime}</span>
            )}
            <button className="btn-ghost !px-2" onClick={refresh} title="Refresh from Excel">
              <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
            </button>
            <button className="btn-ghost !px-2" onClick={toggle} title="Toggle theme">
              {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </div>
        </header>
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
