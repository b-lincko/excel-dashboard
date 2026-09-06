import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  ClipboardList,
  FileText,
  FolderOpen,
  LayoutDashboard,
  ListTodo,
  LogOut,
  Menu,
  Moon,
  RefreshCw,
  Search,
  Settings,
  Shield,
  Sun,
  Truck,
  Upload,
  UserRound,
  Users,
  MessageSquare,
  FolderKanban,
  UserCheck,
  X,
} from "lucide-react";
import { useAuth } from "../context/AuthContext.jsx";
import { useTheme } from "../context/ThemeContext.jsx";
import { useUi } from "../context/UiContext.jsx";
import { api } from "../lib/api.js";
import { clearDashCache } from "../lib/widgets.js";
import ErrorBoundary from "./ErrorBoundary.jsx";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true, group: "Work", page: "dashboard" },
  { to: "/work-orders", label: "Work orders", icon: ClipboardList, group: "Work", page: "work_orders" },
  { to: "/open", label: "Open", icon: FolderOpen, group: "Work", page: "open" },
  { to: "/placed", label: "Placed", icon: Truck, group: "Work", page: "placed" },
  { to: "/overdue", label: "Overdue", icon: AlertTriangle, group: "Work", page: "overdue" },
  { to: "/closed", label: "Closed", icon: CheckCircle2, group: "Work", page: "closed" },
  { to: "/queue", label: "Action queue", icon: ListTodo, group: "Ops", page: "queue" },
  { to: "/suppliers", label: "Suppliers / PO", icon: Truck, group: "Ops", page: "suppliers" },
  { to: "/analytics", label: "Analytics", icon: BarChart3, perm: "analytics", group: "Ops", page: "analytics" },
  { to: "/reports", label: "Reports", icon: FileText, perm: "reports", group: "Ops", page: "reports" },
  { to: "/chat", label: "Chat", icon: MessageSquare, group: "Ops", page: "chat" },
  { to: "/projects", label: "Projects", icon: FolderKanban, group: "Ops", page: "projects" },
  { to: "/import", label: "Import", icon: Upload, perm: "edit", group: "Ops", page: "import" },
  { to: "/performance", label: "Performance", icon: UserCheck, perm: "analytics", group: "Admin", page: "performance" },
  { to: "/audit", label: "Audit log", icon: Shield, perm: "audit", group: "Admin" },
  { to: "/users", label: "Users", icon: Users, perm: "users", group: "Admin" },
  { to: "/settings", label: "Settings", icon: Settings, perm: "settings", group: "Admin" },
];

const TITLES = {
  "/": "Dashboard",
  "/work-orders": "Work orders",
  "/open": "Open orders",
  "/placed": "Placed orders",
  "/overdue": "Overdue",
  "/closed": "Closed orders",
  "/queue": "Action queue",
  "/suppliers": "Suppliers",
  "/analytics": "Analytics",
  "/reports": "Reports",
  "/chat": "Chat",
  "/projects": "Projects",
  "/import": "Import / transfer",
  "/performance": "Employee performance",
  "/audit": "Audit log",
  "/users": "Users",
  "/settings": "Settings",
  "/account": "Account",
};

export default function Layout() {
  const { user, logout, can, canPage } = useAuth();
  const { theme, toggle } = useTheme();
  const { toast, ask } = useUi();
  const nav = useNavigate();
  const loc = useLocation();
  const [sync, setSync] = useState(null);
  const [q, setQ] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [menu, setMenu] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const fileRef = useRef(null);
  const searchRef = useRef(null);
  const accountRef = useRef(null);

  useEffect(() => {
    const title = Object.entries(TITLES).find(([path]) => (path === "/" ? loc.pathname === "/" : loc.pathname.startsWith(path)));
    document.title = title ? `${title[1]} · Linkco MR` : "Linkco MR";
  }, [loc.pathname]);

  useEffect(() => {
    setMenu(false);
    setAccountOpen(false);
  }, [loc.pathname]);

  useEffect(() => {
    function onKey(e) {
      const tag = (e.target?.tagName || "").toLowerCase();
      const typing = tag === "input" || tag === "textarea" || tag === "select" || e.target?.isContentEditable;
      if (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        searchRef.current?.focus();
      }
      if (e.key === "Escape") {
        setMenu(false);
        setAccountOpen(false);
      }
    }
    function onClick(e) {
      if (accountRef.current && !accountRef.current.contains(e.target)) setAccountOpen(false);
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, []);

  async function loadSync() {
    try {
      const next = await api.get("/api/sync/ping");
      setSync((prev) => {
        if (next.sync_token && prev?.sync_token && prev.sync_token !== next.sync_token) {
          window.dispatchEvent(new CustomEvent("woms:data", { detail: next }));
        }
        return { ...prev, ...next };
      });
    } catch (e) {
      setSync((prev) =>
        prev && (prev.synchronized || prev.record_count)
          ? { ...prev, stale: true, warning: e.message }
          : {
              synchronized: false,
              error: e.offline ? e.message : "Excel file is currently unavailable.",
              offline: !!e.offline,
            }
      );
    }
  }

  useEffect(() => {
    api
      .get("/api/sync/status")
      .then(setSync)
      .catch((e) => {
        setSync({
          synchronized: false,
          error: e.offline ? e.message : "Excel file is currently unavailable.",
          offline: !!e.offline,
        });
      });
    const id = setInterval(loadSync, 3000);
    return () => clearInterval(id);
  }, []);

  async function onUpload(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await api.upload("/api/sync/upload", fd);
      setSync(res.sync);
      window.dispatchEvent(new CustomEvent("woms:data", { detail: res.sync }));
      toast(`Workbook scanned · ${res.sync?.record_count ?? 0} rows`, "success");
    } catch (err) {
      toast(err.message || "Upload failed", "error");
    } finally {
      setUploading(false);
    }
  }

  async function refresh() {
    setRefreshing(true);
    try {
      const next = await api.post("/api/sync/refresh");
      clearDashCache();
      setSync(next);
      window.dispatchEvent(new CustomEvent("woms:data", { detail: next }));
      toast("Hard refresh from Excel", "success");
    } catch (e) {
      setSync((prev) => ({ ...(prev || {}), stale: true, warning: e.message }));
      toast(e.message || "Refresh failed", "error");
    } finally {
      setRefreshing(false);
    }
  }

  async function signOut() {
    const ok = await ask({ title: "Sign out?", body: "You will need your password to continue.", confirmLabel: "Sign out" });
    if (!ok) return;
    await logout();
    nav("/login");
  }

  const items = NAV.filter((n) => (!n.perm || can(n.perm)) && (!n.page || canPage(n.page)));
  const groups = [];
  items.forEach((n) => {
    const last = groups[groups.length - 1];
    if (!last || last.group !== n.group) groups.push({ group: n.group, items: [n] });
    else last.items.push(n);
  });

  const sidebar = (
    <>
      <div className="px-5 py-5 flex items-center gap-3">
        <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-cyan-400 to-brand-700 grid place-items-center font-extrabold text-white shadow-lg">
          WO
        </div>
        <div className="min-w-0">
          <div className="font-bold tracking-tight text-white leading-tight">Linkco MR</div>
          <div className="text-[11px] text-slate-400 truncate">IM Work Order · Material Request</div>
        </div>
        <button className="ml-auto lg:hidden btn-ghost !text-slate-300 !px-2" onClick={() => setMenu(false)} aria-label="Close menu">
          <X size={18} />
        </button>
      </div>
      <nav className="px-3 flex-1 space-y-4 overflow-y-auto" aria-label="Main">
        {groups.map((g) => (
          <div key={g.group}>
            <div className="px-3 mb-1 text-[10px] uppercase tracking-wider text-slate-500">{g.group}</div>
            <div className="space-y-0.5">
              {g.items.map((n) => (
                <NavLink
                  key={n.to}
                  to={n.to}
                  end={n.end}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition ${
                      isActive ? "bg-white/10 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"
                    }`
                  }
                >
                  <n.icon size={16} />
                  {n.label}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>
      <div className="p-4 border-t border-white/5">
        <NavLink to="/account" className="block text-xs text-slate-400 mb-1 truncate hover:text-white">
          {user?.full_name || user?.username}
        </NavLink>
        <div className="flex items-center justify-between">
          <span className="text-[11px] uppercase tracking-wider text-cyan-300/80">{user?.role}</span>
          <button className="btn-ghost !text-slate-400 !px-2 !py-1" onClick={signOut} title="Sign out" aria-label="Sign out">
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </>
  );

  return (
    <div className="min-h-screen flex bg-slate-50 dark:bg-ink-900">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-3 focus:rounded-lg focus:bg-white focus:px-3 focus:py-2">
        Skip to content
      </a>
      {menu && <button className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => setMenu(false)} aria-label="Close menu overlay" />}
      <aside className="hidden lg:flex w-[250px] shrink-0 bg-ink-900 text-slate-200 flex-col border-r border-white/5">{sidebar}</aside>
      <aside
        className={`fixed z-40 inset-y-0 left-0 w-[250px] bg-ink-900 text-slate-200 flex flex-col border-r border-white/5 transition-transform lg:hidden ${
          menu ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {sidebar}
      </aside>
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-16 shrink-0 bg-white/90 dark:bg-ink-800/90 backdrop-blur border-b border-slate-200 dark:border-white/5 flex items-center gap-3 px-3 sm:px-6">
          <button className="lg:hidden btn-ghost !px-2" onClick={() => setMenu(true)} aria-label="Open menu">
            <Menu size={18} />
          </button>
          <form
            className="flex-1 max-w-xl relative flex items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              nav(`/work-orders?q=${encodeURIComponent(q)}`);
            }}
          >
            <div className="relative flex-1">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                ref={searchRef}
                id="global-search"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search MRs, technicians, PO, remarks…  /"
                className="pl-9"
                aria-label="Search work orders"
              />
            </div>
            <button type="submit" className="btn-outline !px-2 sm:!px-2.5 !py-1.5 text-xs whitespace-nowrap" title="Search Excel records now">
              Hard search
            </button>
          </form>
          <div className="flex items-center gap-1.5 sm:gap-2 text-xs">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 font-medium ${
                sync?.stale
                  ? "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-300"
                  : sync?.synchronized
                    ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
                    : "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300"
              }`}
              title={sync?.error || sync?.path || ""}
            >
              <Activity size={12} />
              <span className="hidden sm:inline">
                {sync?.stale ? "Updating…" : sync?.synchronized ? "Live" : sync?.error ? "Excel down" : "Checking…"}
              </span>
            </span>
            {can("edit") && (
              <>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  className="hidden"
                  onChange={onUpload}
                />
                <button
                  className="btn-outline !px-2 sm:!px-2.5 !py-1.5 text-xs"
                  onClick={() => fileRef.current?.click()}
                  disabled={uploading}
                  title="Upload Excel workbook"
                >
                  <Upload size={14} className={uploading ? "animate-pulse" : ""} />
                  <span className="hidden md:inline">{uploading ? "Scanning…" : "Upload"}</span>
                </button>
              </>
            )}
            <button
              className="btn-outline !px-2 sm:!px-2.5 !py-1.5 text-xs whitespace-nowrap"
              onClick={refresh}
              title="Reload the workbook from disk and drop cached KPIs"
              aria-label="Hard refresh from Excel"
            >
              <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
              <span className="hidden md:inline">{refreshing ? "Refreshing…" : "Hard refresh"}</span>
            </button>
            <button className="btn-ghost !px-2" onClick={toggle} title="Toggle theme" aria-label="Toggle theme">
              {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <div className="relative" ref={accountRef}>
              <button
                className="btn-ghost !px-2 inline-flex items-center gap-1"
                onClick={() => setAccountOpen((v) => !v)}
                aria-haspopup="menu"
                aria-expanded={accountOpen}
              >
                <UserRound size={16} />
                <ChevronDown size={12} className="hidden sm:block" />
              </button>
              {accountOpen && (
                <div role="menu" className="absolute right-0 mt-2 w-52 card p-1 z-30">
                  <button className="w-full text-left px-3 py-2 rounded-lg text-sm hover:bg-slate-50 dark:hover:bg-white/5" onClick={() => nav("/account")}>
                    Account
                  </button>
                  <button className="w-full text-left px-3 py-2 rounded-lg text-sm hover:bg-slate-50 dark:hover:bg-white/5" onClick={signOut}>
                    Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>
        <main id="main" className="flex-1 overflow-auto p-4 sm:p-6">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
