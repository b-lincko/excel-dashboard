import { useEffect, useState } from "react";
import { api } from "../lib/api.js";
import { useUi } from "../context/UiContext.jsx";

export default function Users() {
  const { toast, ask } = useUi();
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ username: "", password: "", full_name: "", email: "", role: "user" });
  const [error, setError] = useState("");
  const [resetFor, setResetFor] = useState(null);
  const [newPw, setNewPw] = useState("");

  function load() {
    api.get("/api/users").then((d) => setItems(d.items || [])).catch((e) => setError(e.message));
  }
  useEffect(load, []);

  async function create(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/api/users", form);
      setForm({ username: "", password: "", full_name: "", email: "", role: "user" });
      toast("User created", "success");
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function toggleActive(u) {
    const ok = await ask({
      title: u.is_active ? `Disable ${u.username}?` : `Enable ${u.username}?`,
      body: u.is_active ? "They will not be able to sign in." : "They will be able to sign in again.",
      confirmLabel: u.is_active ? "Disable" : "Enable",
      danger: u.is_active,
    });
    if (!ok) return;
    await api.put(`/api/users/${u.id}`, { is_active: !u.is_active });
    toast(u.is_active ? "Account disabled" : "Account enabled", "success");
    load();
  }

  async function resetPassword(e) {
    e.preventDefault();
    if (!resetFor) return;
    if (newPw.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    await api.put(`/api/users/${resetFor.id}`, { password: newPw });
    toast(`Password reset for ${resetFor.username}`, "success");
    setResetFor(null);
    setNewPw("");
  }

  return (
    <div className="space-y-5 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Users</h1>
        <p className="text-sm text-slate-500">Administrator, manager and user roles. Passwords are stored only in the app database, not in Excel.</p>
      </div>
      {error && <div className="text-sm text-rose-600">{error}</div>}
      <form onSubmit={create} className="card p-4 grid md:grid-cols-6 gap-3 items-end">
        <div>
          <label className="lbl">Username</label>
          <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required autoComplete="off" />
        </div>
        <div>
          <label className="lbl">Password</label>
          <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required autoComplete="new-password" />
        </div>
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
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            <option value="admin">Administrator</option>
            <option value="manager">Manager</option>
            <option value="user">User</option>
          </select>
        </div>
        <button className="btn-primary">Add user</button>
      </form>
      {resetFor && (
        <form onSubmit={resetPassword} className="card p-4 flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[200px]">
            <label className="lbl">New password for {resetFor.username}</label>
            <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} autoFocus autoComplete="new-password" />
          </div>
          <button className="btn-primary">Set password</button>
          <button type="button" className="btn-outline" onClick={() => setResetFor(null)}>
            Cancel
          </button>
        </form>
      )}
      <div className="card overflow-hidden">
        <table className="data">
          <thead>
            <tr>
              <th>Username</th>
              <th>Name</th>
              <th>Role</th>
              <th>Active</th>
              <th>Last sign-in</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((u) => (
              <tr key={u.id} className="!cursor-default">
                <td className="font-medium">{u.username}</td>
                <td>{u.full_name}</td>
                <td className="capitalize">{u.role}</td>
                <td>{u.is_active ? "Yes" : "No"}</td>
                <td className="font-mono text-xs">{u.last_login || "—"}</td>
                <td className="space-x-2 whitespace-nowrap">
                  <button className="btn-outline !py-1 !px-2 text-xs" onClick={() => { setResetFor(u); setNewPw(""); }}>
                    Reset password
                  </button>
                  <button className="btn-outline !py-1 !px-2 text-xs" onClick={() => toggleActive(u)}>
                    {u.is_active ? "Disable" : "Enable"}
                  </button>
                </td>
              </tr>
            ))}
            {!items.length && (
              <tr className="!cursor-default">
                <td colSpan={6} className="text-center text-slate-400 py-8">
                  No users found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
