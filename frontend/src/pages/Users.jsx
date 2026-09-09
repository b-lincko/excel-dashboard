import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api.js";
import { GUEST_PAGES, useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";

const PAGE_LABELS = {
  dashboard: "Dashboard",
  work_orders: "Work orders",
  open: "Open",
  placed: "Placed",
  overdue: "Overdue",
  closed: "Closed",
  queue: "Action queue",
  alerts: "SLA alerts",
  suppliers: "Suppliers / PO",
  analytics: "Analytics",
  reports: "Reports",
  chat: "Chat",
  projects: "Projects",
  import: "Import",
  performance: "Performance",
  handover: "Handover",
  health: "Excel health",
  digest: "Morning digest",
  materials: "Materials",
  supplier_suggest: "Supplier suggest",
  po_approvals: "Purchase Approval",
};

const ACTION_LABELS = {
  view: "View records",
  edit: "Edit records",
  create: "Create material requests",
  delete: "Delete records",
  reports: "Reports",
  analytics: "Analytics",
  settings: "Settings",
  users: "User management",
  audit: "Audit log",
  backup: "Backup / restore",
  import: "Import files",
  po_dispatch: "Assign POs / send to Accounts",
  po_approve: "Sign / return POs",
  accounts: "Accounts inbox",
};

const ROLE_LABELS = {
  admin: "Administrator",
  manager: "Manager",
  user: "User",
  readonly: "Read only",
  guest: "Guest",
};

const emptyForm = () => ({
  username: "",
  password: "",
  password2: "",
  full_name: "",
  email: "",
  role: "user",
  is_active: true,
  extra_permissions: [],
});

export default function Users() {
  const { user: me, refresh } = useAuth();
  const { toast, ask } = useUi();
  const [items, setItems] = useState([]);
  const [catalog, setCatalog] = useState({ actions: [], pages: GUEST_PAGES, role_defaults: {}, roles: Object.keys(ROLE_LABELS) });
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState(null);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm());
  const [tab, setTab] = useState("profile");
  const [newPw, setNewPw] = useState("");
  const [newPw2, setNewPw2] = useState("");

  function load() {
    api
      .get("/api/users")
      .then((d) => setItems(d.items || []))
      .catch((e) => setError(e.message));
  }

  useEffect(() => {
    load();
    api
      .get("/api/users/access-catalog")
      .then(setCatalog)
      .catch(() => {});
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((u) =>
      [u.username, u.full_name, u.email, u.role].some((v) => String(v || "").toLowerCase().includes(q))
    );
  }, [items, query]);

  function openCreate() {
    setError("");
    setMode("create");
    setEditing(null);
    setForm(emptyForm());
    setTab("profile");
    setNewPw("");
    setNewPw2("");
  }

  function openEdit(u) {
    setError("");
    setMode("edit");
    setEditing(u);
    setForm({
      username: u.username,
      password: "",
      password2: "",
      full_name: u.full_name || "",
      email: u.email || "",
      role: u.role,
      is_active: !!u.is_active,
      extra_permissions: [...(u.extra_permissions || [])],
    });
    setTab("profile");
    setNewPw("");
    setNewPw2("");
  }

  function closePanel() {
    setMode(null);
    setEditing(null);
    setError("");
  }

  function roleDefaults(role) {
    if (role === "admin") return catalog.actions.concat(catalog.pages);
    return catalog.role_defaults?.[role] || [];
  }

  function hasAccess(perm) {
    if (form.role === "admin") return true;
    if (roleDefaults(form.role).includes(perm)) return true;
    return form.extra_permissions.includes(perm);
  }

  function toggleAccess(perm) {
    if (form.role === "admin") return;
    if (roleDefaults(form.role).includes(perm) && form.role !== "guest") return;
    const next = form.extra_permissions.includes(perm)
      ? form.extra_permissions.filter((p) => p !== perm)
      : [...form.extra_permissions, perm];
    setForm({ ...form, extra_permissions: next });
  }

  async function saveCreate(e) {
    e.preventDefault();
    setError("");
    if (form.password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (form.password !== form.password2) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await api.post("/api/users", {
        username: form.username.trim(),
        password: form.password,
        full_name: form.full_name,
        email: form.email,
        role: form.role,
        extra_permissions: form.role === "admin" ? [] : form.extra_permissions,
      });
      toast(`Created ${form.username}`, "success");
      closePanel();
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit(e) {
    e.preventDefault();
    if (!editing) return;
    setError("");
    setBusy(true);
    try {
      await api.put(`/api/users/${editing.id}`, {
        full_name: form.full_name,
        email: form.email,
        role: form.role,
        is_active: form.is_active,
        extra_permissions: form.role === "admin" ? [] : form.extra_permissions,
      });
      toast(`Updated ${editing.username}`, "success");
      if (editing.id === me?.id) await refresh?.();
      closePanel();
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function savePassword(e) {
    e.preventDefault();
    if (!editing) return;
    setError("");
    if (newPw.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (newPw !== newPw2) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await api.put(`/api/users/${editing.id}`, { password: newPw });
      toast(`Password set for ${editing.username}`, "success");
      setNewPw("");
      setNewPw2("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function removeUser(u) {
    if (u.username === me?.username) {
      toast("You cannot delete your own account", "error");
      return;
    }
    const ok = await ask({
      title: `Delete ${u.username}?`,
      body: "They will no longer be able to sign in. Material-request history is kept.",
      confirmLabel: "Delete user",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.del(`/api/users/${u.id}`);
      toast(`Deleted ${u.username}`, "success");
      if (editing?.id === u.id) closePanel();
      load();
    } catch (err) {
      toast(err.message || "Could not delete", "error");
    }
  }

  const actions = catalog.actions?.length ? catalog.actions : Object.keys(ACTION_LABELS);
  const pages = catalog.pages?.length ? catalog.pages : GUEST_PAGES;

  return (
    <div className="space-y-5 max-w-6xl" data-tour="users">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Users & access</h1>
          <p className="text-sm text-slate-500">
            Create people, set roles, grant extra pages or actions, reset passwords, or remove accounts. Roles live in
            the app, not in Excel.
          </p>
        </div>
        <button className="btn-primary" type="button" onClick={openCreate}>
          New user
        </button>
      </div>

      <div className="grid lg:grid-cols-[1fr_minmax(320px,420px)] gap-5 items-start">
        <div className="space-y-3 min-w-0">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search name, username, email or role"
            aria-label="Search users"
          />
          <div className="card overflow-hidden">
            <table className="data">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Role</th>
                  <th>Access</th>
                  <th>Active</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((u) => (
                  <tr
                    key={u.id}
                    className={editing?.id === u.id ? "bg-sky-50/80 dark:bg-sky-500/10" : ""}
                    onClick={() => openEdit(u)}
                  >
                    <td>
                      <div className="font-medium">{u.full_name || u.username}</div>
                      <div className="text-xs text-slate-500">
                        {u.username}
                        {u.email ? ` · ${u.email}` : ""}
                        {u.email && u.email_verified ? " · verified" : u.email ? " · unverified" : ""}
                      </div>
                    </td>
                    <td className="capitalize">{ROLE_LABELS[u.role] || u.role}</td>
                    <td className="whitespace-normal text-xs text-slate-500 max-w-[180px]">
                      {u.role === "admin"
                        ? "All"
                        : (u.extra_permissions || []).length
                          ? `Role + ${(u.extra_permissions || []).length}`
                          : "Role default"}
                    </td>
                    <td>{u.is_active ? "Yes" : "No"}</td>
                    <td className="whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                      <button className="btn-outline !py-1 !px-2 text-xs" type="button" onClick={() => openEdit(u)}>
                        Edit
                      </button>
                    </td>
                  </tr>
                ))}
                {!filtered.length && (
                  <tr className="!cursor-default">
                    <td colSpan={5} className="text-center text-slate-400 py-8">
                      No matching users.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {mode && (
          <div className="card p-4 space-y-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="font-semibold">{mode === "create" ? "New user" : `Edit ${editing?.username}`}</div>
                <p className="text-xs text-slate-500">Profile, access and password.</p>
              </div>
              <button type="button" className="btn-ghost !px-2 !py-1 text-xs" onClick={closePanel}>
                Close
              </button>
            </div>

            <div className="tab-bar">
              <button type="button" className={`tab-btn ${tab === "profile" ? "is-on" : ""}`} onClick={() => setTab("profile")}>
                Profile
              </button>
              <button type="button" className={`tab-btn ${tab === "access" ? "is-on" : ""}`} onClick={() => setTab("access")}>
                Access
              </button>
              <button type="button" className={`tab-btn ${tab === "password" ? "is-on" : ""}`} onClick={() => setTab("password")}>
                Password
              </button>
            </div>

            {error && <div className="text-sm text-rose-600">{error}</div>}

            {tab === "profile" && (
              <form onSubmit={mode === "create" ? saveCreate : saveEdit} className="space-y-3">
                <div>
                  <label className="lbl">Username</label>
                  <input
                    value={form.username}
                    onChange={(e) => setForm({ ...form, username: e.target.value })}
                    required
                    autoComplete="off"
                    disabled={mode === "edit"}
                  />
                </div>
                {mode === "create" && (
                  <>
                    <div>
                      <label className="lbl">Password</label>
                      <input
                        type="password"
                        value={form.password}
                        onChange={(e) => setForm({ ...form, password: e.target.value })}
                        required
                        autoComplete="new-password"
                      />
                    </div>
                    <div>
                      <label className="lbl">Confirm password</label>
                      <input
                        type="password"
                        value={form.password2}
                        onChange={(e) => setForm({ ...form, password2: e.target.value })}
                        required
                        autoComplete="new-password"
                      />
                    </div>
                  </>
                )}
                <div>
                  <label className="lbl">Full name</label>
                  <input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
                </div>
                <div>
                  <label className="lbl">Email</label>
                  <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
                </div>
                <div>
                  <label className="lbl">Role</label>
                  <select
                    value={form.role}
                    onChange={(e) => setForm({ ...form, role: e.target.value, extra_permissions: [] })}
                  >
                    {(catalog.roles || Object.keys(ROLE_LABELS)).map((r) => (
                      <option key={r} value={r}>
                        {ROLE_LABELS[r] || r}
                      </option>
                    ))}
                  </select>
                </div>
                {mode === "edit" && (
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="w-auto"
                      checked={form.is_active}
                      onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                    />
                    Active (can sign in)
                  </label>
                )}
                <button className="btn-primary w-full" disabled={busy}>
                  {busy ? "Saving…" : mode === "create" ? "Create user" : "Save profile"}
                </button>
                {mode === "edit" && editing?.username !== me?.username && (
                  <button type="button" className="btn-danger w-full" onClick={() => removeUser(editing)}>
                    Delete user
                  </button>
                )}
              </form>
            )}

            {tab === "access" && (
              <form onSubmit={mode === "create" ? saveCreate : saveEdit} className="space-y-4">
                {form.role === "admin" ? (
                  <p className="text-sm text-slate-500">Administrators already have every page and action.</p>
                ) : form.role === "guest" ? (
                  <>
                    <p className="text-xs text-slate-500">Guests only see the pages you tick. They cannot edit.</p>
                    <div className="space-y-1.5 max-h-72 overflow-auto pr-1">
                      {pages.map((id) => (
                        <AccessRow
                          key={id}
                          id={id}
                          label={PAGE_LABELS[id] || id}
                          locked={false}
                          on={hasAccess(id)}
                          onToggle={() => toggleAccess(id)}
                        />
                      ))}
                    </div>
                  </>
                ) : (
                  <>
                    <p className="text-xs text-slate-500">
                      Ticks from the role cannot be removed. Extra ticks grant this person more than their role.
                      Settings, users, and backup stay with administrators.
                    </p>
                    <div className="space-y-1.5">
                      {actions.map((id) => (
                        <AccessRow
                          key={id}
                          id={id}
                          label={ACTION_LABELS[id] || id}
                          locked={roleDefaults(form.role).includes(id)}
                          on={hasAccess(id)}
                          onToggle={() => toggleAccess(id)}
                        />
                      ))}
                    </div>
                  </>
                )}
                <button className="btn-primary w-full" disabled={busy}>
                  {busy ? "Saving…" : mode === "create" ? "Create user" : "Save access"}
                </button>
              </form>
            )}

            {tab === "password" &&
              (mode === "create" ? (
                <p className="text-sm text-slate-500">Set the password on the Profile tab when creating someone.</p>
              ) : (
                <form onSubmit={savePassword} className="space-y-3">
                  <div>
                    <label className="lbl">New password for {editing?.username}</label>
                    <input
                      type="password"
                      value={newPw}
                      onChange={(e) => setNewPw(e.target.value)}
                      autoComplete="new-password"
                      required
                    />
                  </div>
                  <div>
                    <label className="lbl">Confirm new password</label>
                    <input
                      type="password"
                      value={newPw2}
                      onChange={(e) => setNewPw2(e.target.value)}
                      autoComplete="new-password"
                      required
                    />
                  </div>
                  <button className="btn-primary w-full" disabled={busy}>
                    {busy ? "Saving…" : "Set password"}
                  </button>
                </form>
              ))}
          </div>
        )}
      </div>
    </div>
  );
}

function AccessRow({ id, label, locked, on, onToggle }) {
  return (
    <label className={`flex items-center gap-2 text-sm ${locked ? "opacity-80" : ""}`}>
      <input type="checkbox" className="w-auto" checked={on} disabled={locked} onChange={onToggle} />
      <span>
        {label}
        {locked ? <span className="text-[11px] text-slate-400"> · role</span> : null}
      </span>
      <span className="sr-only">{id}</span>
    </label>
  );
}
