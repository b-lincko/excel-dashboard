import { useEffect, useState } from "react";
import { api } from "../lib/api.js";

export default function Users() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ username: "", password: "", full_name: "", email: "", role: "user" });
  const [error, setError] = useState("");

  function load() {
    api.get("/api/users").then((d) => setItems(d.items || []));
  }
  useEffect(load, []);

  async function create(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/api/users", form);
      setForm({ username: "", password: "", full_name: "", email: "", role: "user" });
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="space-y-5 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Users</h1>
        <p className="text-sm text-slate-500">Administrator, manager and user roles with configurable permissions.</p>
      </div>
      {error && <div className="text-sm text-rose-600">{error}</div>}
      <form onSubmit={create} className="card p-4 grid md:grid-cols-5 gap-3 items-end">
        <div>
          <label className="lbl">Username</label>
          <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required />
        </div>
        <div>
          <label className="lbl">Password</label>
          <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
        </div>
        <div>
          <label className="lbl">Full name</label>
          <input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
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
      <div className="card overflow-hidden">
        <table className="data">
          <thead>
            <tr>
              <th>Username</th>
              <th>Name</th>
              <th>Role</th>
              <th>Active</th>
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
                <td>
                  <button
                    className="btn-outline !py-1 !px-2 text-xs"
                    onClick={async () => {
                      await api.put(`/api/users/${u.id}`, { is_active: !u.is_active });
                      load();
                    }}
                  >
                    {u.is_active ? "Disable" : "Enable"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
