import { useEffect, useState } from "react";
import { api, qs } from "../lib/api.js";

export default function AuditLog() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [wo, setWo] = useState("");
  const [user, setUser] = useState("");
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    api
      .get(`/api/audit${qs({ work_order_id: wo, username: user, limit: 300 })}`)
      .then((d) => {
        setItems(d.items || []);
        setTotal(d.total || 0);
      })
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Audit log</h1>
        <p className="text-sm text-slate-500">{total} events stored separately from the Excel workbook.</p>
      </div>
      <form
        className="flex flex-wrap gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          load();
        }}
      >
        <input placeholder="Work order ID" value={wo} onChange={(e) => setWo(e.target.value)} className="max-w-xs" />
        <input placeholder="Username" value={user} onChange={(e) => setUser(e.target.value)} className="max-w-xs" />
        <button className="btn-primary" type="submit">
          Filter
        </button>
        {(wo || user) && (
          <button
            type="button"
            className="btn-outline"
            onClick={() => {
              setWo("");
              setUser("");
              setLoading(true);
              api
                .get(`/api/audit${qs({ limit: 300 })}`)
                .then((d) => {
                  setItems(d.items || []);
                  setTotal(d.total || 0);
                })
                .finally(() => setLoading(false));
            }}
          >
            Clear
          </button>
        )}
      </form>
      <div className="card overflow-hidden">
        <table className="data">
          <thead>
            <tr>
              <th>Time</th>
              <th>User</th>
              <th>Action</th>
              <th>Work Order</th>
              <th>Field</th>
              <th>Old</th>
              <th>New</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.id} className="!cursor-default">
                <td className="font-mono text-xs">{r.created_at}</td>
                <td>{r.username}</td>
                <td>{r.action}</td>
                <td className="font-mono text-xs">{r.work_order_id}</td>
                <td>{r.field}</td>
                <td className="max-w-[200px] truncate text-slate-500">{r.old_value}</td>
                <td className="max-w-[200px] truncate">{r.new_value || r.details}</td>
              </tr>
            ))}
            {!loading && !items.length && (
              <tr className="!cursor-default">
                <td colSpan={7} className="text-center text-slate-400 py-10">
                  No audit events match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
