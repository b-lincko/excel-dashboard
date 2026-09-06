import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";

const empty = { name: "", owner: "", description: "", start_date: "", due_date: "", status: "active" };

export default function Projects() {
  const { can } = useAuth();
  const { toast, ask } = useUi();
  const nav = useNavigate();
  const [items, setItems] = useState([]);
  const [form, setForm] = useState(empty);
  const [selected, setSelected] = useState(null);
  const [taskTitle, setTaskTitle] = useState("");
  const [woId, setWoId] = useState("");
  const canEdit = can("edit");

  function load() {
    api.get("/api/projects").then((d) => setItems(d.items || [])).catch((e) => toast(e.message, "error"));
  }
  useEffect(load, []);

  async function open(id) {
    const d = await api.get(`/api/projects/${id}`);
    setSelected(d.item);
  }

  async function create(e) {
    e.preventDefault();
    const d = await api.post("/api/projects", form);
    setForm(empty);
    toast("Project created", "success");
    load();
    setSelected(d.item);
  }

  async function addTask(e) {
    e.preventDefault();
    if (!selected || !taskTitle.trim()) return;
    await api.post(`/api/projects/${selected.id}/tasks`, { title: taskTitle.trim() });
    setTaskTitle("");
    open(selected.id);
    load();
  }

  async function toggleTask(t) {
    await api.put(`/api/projects/${selected.id}/tasks/${t.id}`, { status: t.status === "done" ? "open" : "done" });
    open(selected.id);
    load();
  }

  async function linkWo(e) {
    e.preventDefault();
    if (!woId.trim()) return;
    try {
      const rec = await api.get(`/api/work-orders/${encodeURIComponent(woId.trim())}`);
      const rid = rec.item?.record_id || woId.trim();
      await api.post(`/api/projects/${selected.id}/links`, { record_id: rid });
      setWoId("");
      open(selected.id);
      load();
    } catch (err) {
      toast(err.message, "error");
    }
  }

  async function remove() {
    if (!selected) return;
    const ok = await ask({ title: `Delete ${selected.name}?`, body: "Tasks and work-order links are removed. Excel is not changed.", confirmLabel: "Delete", danger: true });
    if (!ok) return;
    await api.del(`/api/projects/${selected.id}`);
    setSelected(null);
    load();
  }

  return (
    <div className="grid lg:grid-cols-[1fr_1.2fr] gap-4">
      <div className="space-y-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Projects</h1>
          <p className="text-sm text-slate-500">Track work in the app database. Link Excel material requests without changing the workbook.</p>
        </div>
        {canEdit && (
          <form onSubmit={create} className="card p-4 space-y-3">
            <div className="font-semibold">New project</div>
            <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Name" />
            <input value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} placeholder="Owner" />
            <textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Description" />
            <div className="grid grid-cols-2 gap-2">
              <input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
              <input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
            </div>
            <button className="btn-primary">Create project</button>
          </form>
        )}
        <div className="card overflow-hidden">
          <table className="data">
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Owner</th>
                <th>Tasks</th>
                <th>MRs</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id} onClick={() => open(p.id)} className={selected?.id === p.id ? "bg-sky-50 dark:bg-white/5" : ""}>
                  <td className="font-medium">{p.name}</td>
                  <td className="capitalize">{p.status}</td>
                  <td>{p.owner || "—"}</td>
                  <td>
                    {p.done_count}/{p.task_count}
                  </td>
                  <td>{p.wo_count}</td>
                </tr>
              ))}
              {!items.length && (
                <tr className="!cursor-default">
                  <td colSpan={5} className="text-center text-slate-400 py-8">
                    No projects yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      <div className="card p-5 space-y-4 min-h-[320px]">
        {!selected ? (
          <div className="text-sm text-slate-500">Select a project to see tasks and linked work orders.</div>
        ) : (
          <>
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold">{selected.name}</h2>
                <p className="text-sm text-slate-500">{selected.description || "No description"}</p>
                <p className="text-xs text-slate-400 mt-1">
                  {selected.owner || "Unassigned"} · {selected.start_date || "—"} → {selected.due_date || "—"}
                </p>
              </div>
              {canEdit && (
                <button className="btn-danger !py-1 !px-2 text-xs" onClick={remove}>
                  Delete
                </button>
              )}
            </div>
            <div>
              <div className="font-semibold mb-2">Tasks</div>
              <ul className="space-y-1">
                {(selected.tasks || []).map((t) => (
                  <li key={t.id} className="flex items-center gap-2 text-sm">
                    <input type="checkbox" className="w-auto" checked={t.status === "done"} disabled={!canEdit} onChange={() => toggleTask(t)} />
                    <span className={t.status === "done" ? "line-through text-slate-400" : ""}>{t.title}</span>
                  </li>
                ))}
              </ul>
              {canEdit && (
                <form onSubmit={addTask} className="flex gap-2 mt-2">
                  <input value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)} placeholder="Add a task" />
                  <button className="btn-outline">Add</button>
                </form>
              )}
            </div>
            <div>
              <div className="font-semibold mb-2">Linked material requests</div>
              <ul className="space-y-1">
                {(selected.links || []).map((l) => (
                  <li key={l.record_id}>
                    <button className="text-sm text-brand-700 hover:underline" onClick={() => nav(`/work-orders/${encodeURIComponent(l.record_id)}`)}>
                      {l.record_id}
                    </button>
                  </li>
                ))}
              </ul>
              {canEdit && (
                <form onSubmit={linkWo} className="flex gap-2 mt-2">
                  <input value={woId} onChange={(e) => setWoId(e.target.value)} placeholder="IM WO # or record id" />
                  <button className="btn-outline">Link</button>
                </form>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
