import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  Bell,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
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
  PackageSearch,
  Settings,
  Shield,
  Sun,
  Truck,
  Upload,
  UserRound,
  Users,
  MessageSquare,
  FolderKanban,
  Keyboard,
  UserCheck,
  ClipboardCheck,
  FileWarning,
  X,
} from "lucide-react";
import { useAuth } from "../context/AuthContext.jsx";
import { useTheme } from "../context/ThemeContext.jsx";
import { useUi } from "../context/UiContext.jsx";
import { api } from "../lib/api.js";
import { clearDashCache } from "../lib/widgets.js";
import ErrorBoundary from "./ErrorBoundary.jsx";
import CommandPalette from "./CommandPalette.jsx";
import { useTour } from "../context/TourContext.jsx";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true, group: "Daily", page: "dashboard" },
  { to: "/queue", label: "Action queue", icon: ListTodo, group: "Daily", page: "queue" },
  { to: "/work-orders", label: "Work orders", icon: ClipboardList, group: "Daily", page: "work_orders" },
  { to: "/open", label: "Open", icon: FolderOpen, group: "Daily", page: "open" },
  { to: "/overdue", label: "Overdue", icon: AlertTriangle, group: "Daily", page: "overdue" },
  { to: "/chat", label: "Chat", icon: MessageSquare, group: "Daily", page: "chat" },
  { to: "/placed", label: "Placed", icon: Truck, group: "Lists", page: "placed" },
  { to: "/closed", label: "Closed", icon: CheckCircle2, group: "Lists", page: "closed" },
  { to: "/guide", label: "Guide", icon: CircleHelp, group: "Lists" },
  { to: "/digest", label: "Morning digest", icon: ClipboardCheck, group: "Ops", page: "digest" },
  { to: "/alerts", label: "SLA alerts", icon: Bell, group: "Ops", page: "alerts" },
  { to: "/handover", label: "Handover", icon: ClipboardCheck, group: "Ops", page: "handover" },
  { to: "/health", label: "Excel health", icon: FileWarning, group: "Ops", page: "health" },
  { to: "/suppliers", label: "Suppliers / PO", icon: Truck, group: "Ops", page: "suppliers" },
  { to: "/materials", label: "Materials", icon: Search, group: "Ops", page: "materials" },
  { to: "/supplier-suggest", label: "Supplier suggest", icon: PackageSearch, group: "Ops", page: "supplier_suggest" },
  { to: "/analytics", label: "Analytics", icon: BarChart3, perm: "analytics", group: "Ops", page: "analytics" },
  { to: "/reports", label: "Reports", icon: FileText, perm: "reports", group: "Ops", page: "reports" },
  { to: "/projects", label: "Projects", icon: FolderKanban, group: "Ops", page: "projects" },
  { to: "/import", label: "Import", icon: Upload, perm: "edit", group: "Ops", page: "import" },
  { to: "/performance", label: "Performance", icon: UserCheck, perm: "analytics", group: "Admin", page: "performance" },
  { to: "/audit", label: "Audit log", icon: Shield, perm: "audit", group: "Admin" },
  { to: "/users", label: "Users", icon: Users, perm: "users", group: "Admin" },
  { to: "/settings", label: "Settings", icon: Settings, perm: "settings", group: "Admin" },
];

const NAV_COLLAPSE_DEFAULT = { Lists: true, Ops: true, Admin: true };

function readNavCollapsed() {
  try {
    const raw = JSON.parse(localStorage.getItem("woms.nav.collapsed") || "null");
    if (raw && typeof raw === "object") return { ...NAV_COLLAPSE_DEFAULT, ...raw };
  } catch {
    /* ignore */
  }
  return { ...NAV_COLLAPSE_DEFAULT };
}

const TITLES = {
  "/": "Dashboard",
  "/work-orders": "Work orders",
  "/open": "Open orders",
  "/placed": "Placed orders",
  "/overdue": "Overdue",
  "/closed": "Closed orders",
  "/queue": "Action queue",
  "/digest": "Morning digest",
  "/alerts": "SLA alerts",
  "/handover": "Handover",
  "/health": "Excel health",
  "/suppliers": "Suppliers",
  "/materials": "Materials",
  "/supplier-suggest": "Supplier suggestions",
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
  "/guide": "Guide",
};

export default function Layout() {
  const { user, logout, can, canPage } = useAuth();
  const { theme, toggle } = useTheme();
  const { toast, ask } = useUi();
  const { start: startTour, active: tourActive } = useTour();
  const nav = useNavigate();
  const loc = useLocation();
  const [sync, setSync] = useState(null);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState([]);
  const [hitsOpen, setHitsOpen] = useState(false);
  const [hitIdx, setHitIdx] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [menu, setMenu] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [inboxOpen, setInboxOpen] = useState(false);
  const [inbox, setInbox] = useState({ items: [], unread: 0 });
  const searchRef = useRef(null);
  const accountRef = useRef(null);
  const inboxRef = useRef(null);
  const [navCollapsed, setNavCollapsed] = useState(readNavCollapsed);

  useEffect(() => {
    const title = Object.entries(TITLES).find(([path]) => (path === "/" ? loc.pathname === "/" : loc.pathname.startsWith(path)));
    document.title = title ? `${title[1]} · Linkco MR` : "Linkco MR";
  }, [loc.pathname]);

  useEffect(() => {
    setMenu(false);
    setAccountOpen(false);
    setInboxOpen(false);
    setHitsOpen(false);
  }, [loc.pathname]);

  useEffect(() => {
    let chord = "";
    let chordTimer;
    function onKey(e) {
      const tag = (e.target?.tagName || "").toLowerCase();
      const typing = tag === "input" || tag === "textarea" || tag === "select" || e.target?.isContentEditable;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
        return;
      }
      if (e.key === "Escape") {
        setMenu(false);
        setAccountOpen(false);
        setInboxOpen(false);
        setHitsOpen(false);
        setPaletteOpen(false);
        return;
      }
      if (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey && !e.shiftKey) {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (e.key === "?" && !typing) {
        e.preventDefault();
        if (!tourActive) nav("/guide");
        return;
      }
      if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key.toLowerCase() === "n" && can("create")) {
        e.preventDefault();
        nav("/work-orders/new");
        return;
      }
      if (e.key.toLowerCase() === "g") {
        chord = "g";
        window.clearTimeout(chordTimer);
        chordTimer = window.setTimeout(() => {
          chord = "";
        }, 900);
        return;
      }
      if (chord === "g") {
        chord = "";
        window.clearTimeout(chordTimer);
        const map = { q: "/queue", w: "/work-orders", d: "/", c: "/chat", g: "/guide" };
        const to = map[e.key.toLowerCase()];
        if (to) {
          e.preventDefault();
          nav(to);
        }
      }
    }
    function onClick(e) {
      if (accountRef.current && !accountRef.current.contains(e.target)) setAccountOpen(false);
      if (inboxRef.current && !inboxRef.current.contains(e.target)) setInboxOpen(false);
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.clearTimeout(chordTimer);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, [nav, tourActive, can]);

  function loadInbox() {
    api
      .get("/api/notifications?limit=40")
      .then(setInbox)
      .catch(() => {});
  }

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
              error: e.offline ? e.message : "Could not reach the server.",
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
          error: e.offline ? e.message : "Could not reach the server.",
          offline: !!e.offline,
        });
      });
    const id = setInterval(loadSync, 8000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    loadInbox();
    const id = setInterval(loadInbox, 8000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const query = q.trim();
    if (query.length < 1) {
      setHits([]);
      return undefined;
    }
    const timer = setTimeout(() => {
      api
        .get(`/api/work-orders/suggest?q=${encodeURIComponent(query)}&limit=6`)
        .then((d) => {
          const groups = d.groups || {};
          const rows = [];
          (groups.orders || []).forEach((o) =>
            rows.push({
              key: `o-${o.record_id}`,
              kind: "order",
              label: o.label,
              hint: o.hint,
              extra: o.description,
              to: `/work-orders/${encodeURIComponent(o.record_id)}`,
            })
          );
          (groups.suppliers || []).forEach((s) =>
            rows.push({
              key: `s-${s.label}`,
              kind: "supplier",
              label: s.label,
              hint: "Supplier",
              to: `/work-orders?q=${encodeURIComponent(s.label)}`,
            })
          );
          (groups.materials || []).forEach((m) =>
            rows.push({
              key: `m-${m.label}`,
              kind: "material",
              label: m.label,
              hint: m.hint,
              to: `/work-orders?q=${encodeURIComponent(m.label)}`,
            })
          );
          (groups.people || []).forEach((p) =>
            rows.push({
              key: `p-${p.username || p.label}`,
              kind: "person",
              label: p.full_name || p.label,
              hint: p.username || p.hint,
              to: `/work-orders?assigned_to=${encodeURIComponent(p.full_name || p.label)}`,
            })
          );
          (groups.sites || []).forEach((s) =>
            rows.push({
              key: `site-${s.id || s.label}`,
              kind: "site",
              label: s.label,
              hint: s.hint || "Site",
              to: `/work-orders?department=${encodeURIComponent(s.id || s.label)}`,
            })
          );
          setHits(rows.slice(0, 12));
          setHitIdx(0);
          setHitsOpen(true);
        })
        .catch(() => setHits([]));
    }, 220);
    return () => clearTimeout(timer);
  }, [q]);

  async function refresh() {
    setRefreshing(true);
    try {
      const next = await api.post("/api/sync/refresh");
      clearDashCache();
      setSync(next);
      window.dispatchEvent(new CustomEvent("woms:data", { detail: next }));
      toast("Records reloaded", "success");
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
  const activeGroup =
    items.find((n) => (n.end ? loc.pathname === n.to : loc.pathname === n.to || loc.pathname.startsWith(`${n.to}/`)))
      ?.group || "Daily";

  function toggleNavGroup(group) {
    if (group === "Daily") return;
    setNavCollapsed((prev) => {
      const next = { ...prev, [group]: !prev[group] };
      try {
        localStorage.setItem("woms.nav.collapsed", JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  }

  const sidebar = (
    <>
      <div className="px-5 py-5 flex items-center gap-3">
        <div className="h-10 w-10 rounded-xl bg-brand-600 grid place-items-center font-extrabold text-white">
          WO
        </div>
        <div className="min-w-0">
          <div className="font-bold tracking-tight text-slate-900 dark:text-white leading-tight">Linkco MR</div>
          <div className="text-[11px] text-slate-400 truncate">Work orders · Material requests</div>
        </div>
        <button className="ml-auto lg:hidden btn-ghost !px-2" onClick={() => setMenu(false)} aria-label="Close menu">
          <X size={18} />
        </button>
      </div>
      <nav className="px-3 flex-1 space-y-3 overflow-y-auto pb-3" aria-label="Main">
        {groups.map((g) => {
          const folded = g.group !== "Daily" && navCollapsed[g.group] && activeGroup !== g.group;
          return (
            <div key={g.group} data-tour={g.group === "Daily" ? "nav-work" : undefined}>
              <button
                type="button"
                className="w-full px-3 mb-1 flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                onClick={() => toggleNavGroup(g.group)}
                aria-expanded={!folded}
              >
                {g.group}
                {g.group !== "Daily" && <ChevronDown size={12} className={folded ? "-rotate-90 transition" : "transition"} />}
              </button>
              {!folded && (
                <div className="space-y-0.5">
                  {g.items.map((n) => (
                    <NavLink
                      key={n.to}
                      to={n.to}
                      end={n.end}
                      className={({ isActive }) =>
                        `nav-link ${
                          isActive
                            ? "is-on"
                            : "text-slate-600 hover:text-slate-900 hover:bg-slate-50 dark:text-slate-400 dark:hover:text-white dark:hover:bg-white/5"
                        }`
                      }
                    >
                      <n.icon size={16} />
                      {n.label}
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </nav>
      <div className="p-4 border-t border-slate-100 dark:border-white/5">
        <NavLink to="/account" className="block text-xs text-slate-500 mb-1 truncate hover:text-brand-700 dark:text-slate-400 dark:hover:text-white">
          {user?.full_name || user?.username}
        </NavLink>
        <div className="flex items-center justify-between">
          <span className="text-[11px] uppercase tracking-wider text-brand-700 dark:text-brand-400">{user?.role}</span>
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
      <aside className="hidden lg:flex w-[250px] shrink-0 bg-white dark:bg-ink-900 text-slate-700 flex-col border-r border-slate-200 dark:border-white/5">{sidebar}</aside>
      <aside
        className={`fixed z-40 inset-y-0 left-0 w-[250px] bg-white dark:bg-ink-900 text-slate-700 flex flex-col border-r border-slate-200 dark:border-white/5 transition-transform lg:hidden ${
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
            data-tour="search"
            className="flex-1 max-w-xl relative flex items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              setHitsOpen(false);
              nav(`/work-orders?q=${encodeURIComponent(q)}`);
            }}
          >
            <div className="relative flex-1">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                ref={searchRef}
                id="global-search"
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setHitsOpen(true);
                }}
                onFocus={() => hits.length && setHitsOpen(true)}
                onBlur={() => setTimeout(() => setHitsOpen(false), 150)}
                onKeyDown={(e) => {
                  if (!hitsOpen || !hits.length) return;
                  if (e.key === "ArrowDown") {
                    e.preventDefault();
                    setHitIdx((n) => (n + 1) % hits.length);
                  } else if (e.key === "ArrowUp") {
                    e.preventDefault();
                    setHitIdx((n) => (n - 1 + hits.length) % hits.length);
                  } else if (e.key === "Enter" && hits[hitIdx]) {
                    e.preventDefault();
                    setHitsOpen(false);
                    nav(hits[hitIdx].to);
                  }
                }}
                placeholder="Search WO, supplier, item, person, site…  /"
                className="pl-9"
                aria-label="Search work orders"
                autoComplete="off"
              />
              {hitsOpen && hits.length > 0 && (
                <div className="absolute left-0 right-0 top-full z-30 mt-1 card p-1 max-h-80 overflow-auto">
                  {hits.map((r, i) => (
                    <button
                      key={r.key}
                      type="button"
                      className={`w-full text-left px-3 py-2 rounded-lg text-sm ${i === hitIdx ? "bg-slate-100 dark:bg-white/10" : "hover:bg-slate-50 dark:hover:bg-white/5"}`}
                      onMouseDown={(e) => {
                        e.preventDefault();
                        setHitsOpen(false);
                        nav(r.to);
                      }}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="font-medium truncate">{r.label}</div>
                        <span className="text-[10px] uppercase tracking-wider text-slate-400">{r.kind}</span>
                      </div>
                      {r.hint ? <div className="text-[11px] text-slate-500 truncate">{r.hint}</div> : null}
                      {r.extra ? <div className="text-xs text-slate-500 truncate">{r.extra}</div> : null}
                    </button>
                  ))}
                  <button
                    type="button"
                    className="w-full text-left px-3 py-2 text-xs text-brand-700 dark:text-cyan-300"
                    onMouseDown={(e) => {
                      e.preventDefault();
                      setHitsOpen(false);
                      nav(`/work-orders?q=${encodeURIComponent(q)}`);
                    }}
                  >
                    View all matches
                  </button>
                </div>
              )}
            </div>
          </form>
          <div className="flex items-center gap-1.5 sm:gap-2 text-xs">
            <span
              data-tour="live"
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
                {sync?.stale
                  ? "Updating…"
                  : sync?.synchronized
                    ? sync?.excel_backup === false
                      ? "Live · backup off"
                      : "Live"
                    : sync?.error
                      ? "Offline"
                      : "Checking…"}
              </span>
            </span>
            <button
              className="btn-outline !px-2 sm:!px-2.5 !py-1.5 text-xs whitespace-nowrap"
              onClick={refresh}
              title="Reload records from the database"
              aria-label="Refresh records"
            >
              <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
              <span className="hidden md:inline">{refreshing ? "Refreshing…" : "Refresh"}</span>
            </button>
            <div className="relative" ref={inboxRef}>
              <button
                className="btn-ghost !px-2 relative"
                onClick={() => {
                  setInboxOpen((v) => !v);
                  loadInbox();
                }}
                title="Notifications"
                aria-label="Notifications"
              >
                <Bell size={16} />
                {inbox.unread > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-rose-600 text-white text-[10px] grid place-items-center">
                    {inbox.unread > 9 ? "9+" : inbox.unread}
                  </span>
                )}
              </button>
              {inboxOpen && (
                <div className="absolute right-0 mt-2 w-80 card p-1 z-30">
                  <div className="flex items-center justify-between px-3 py-2">
                    <div className="text-sm font-semibold">Inbox</div>
                    {inbox.unread > 0 && (
                      <button
                        className="text-xs text-brand-700 dark:text-cyan-300"
                        onClick={async () => {
                          await api.post("/api/notifications/read", {});
                          loadInbox();
                        }}
                      >
                        Mark all read
                      </button>
                    )}
                  </div>
                  <div className="max-h-80 overflow-y-auto">
                    {(inbox.items || []).map((n) => (
                      <button
                        key={n.id}
                        type="button"
                        className={`w-full text-left px-3 py-2 rounded-lg text-sm hover:bg-slate-50 dark:hover:bg-white/5 ${n.read_at ? "" : "bg-sky-50/60 dark:bg-sky-500/10"}`}
                        onClick={async () => {
                          await api.post("/api/notifications/read", { ids: [n.id] });
                          loadInbox();
                          if (n.record_id) nav(`/work-orders/${encodeURIComponent(n.record_id)}`);
                          else if (n.thread_id) nav(`/chat?thread=${encodeURIComponent(n.thread_id)}`);
                          else nav("/chat");
                          setInboxOpen(false);
                        }}
                      >
                        <div className="text-[11px] uppercase tracking-wider text-slate-400">{n.kind}</div>
                        <div className="text-sm leading-snug">{n.body}</div>
                        <div className="text-[11px] text-slate-400 mt-0.5">{n.created_at}</div>
                      </button>
                    ))}
                    {!inbox.items?.length && <div className="px-3 py-6 text-sm text-slate-500">No messages yet.</div>}
                  </div>
                </div>
              )}
            </div>
            <button
              className="btn-ghost !px-2"
              data-tour="command"
              onClick={() => setPaletteOpen(true)}
              title="Command palette (Ctrl/⌘+K)"
              aria-label="Open command palette"
            >
              <Keyboard size={16} />
            </button>
            <button className="btn-ghost !px-2" onClick={() => nav("/guide")} title="Guide (?)" aria-label="Open guide">
              <CircleHelp size={16} />
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
                  <button className="w-full text-left px-3 py-2 rounded-lg text-sm hover:bg-slate-50 dark:hover:bg-white/5" onClick={() => nav("/guide")}>
                    Guide
                  </button>
                  <button
                    className="w-full text-left px-3 py-2 rounded-lg text-sm hover:bg-slate-50 dark:hover:bg-white/5"
                    onClick={() => {
                      setAccountOpen(false);
                      if (!tourActive) startTour();
                    }}
                  >
                    Start tour
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
          <ErrorBoundary resetKey={loc.pathname}>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
