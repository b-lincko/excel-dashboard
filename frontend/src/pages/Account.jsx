import { useState } from "react";
import { api } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";

export default function Account() {
  const { user } = useAuth();
  const { toast } = useUi();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save(e) {
    e.preventDefault();
    setError("");
    if (next.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    if (next !== again) {
      setError("New passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await api.post("/api/auth/password", { current_password: current, new_password: next });
      setCurrent("");
      setNext("");
      setAgain("");
      toast("Password updated.", "success");
    } catch (err) {
      setError(err.message || "Could not update password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5 max-w-xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Account</h1>
        <p className="text-sm text-slate-500">Your profile and sign-in credentials. Work order data stays in Excel.</p>
      </div>
      <div className="card p-5 space-y-2 text-sm">
        <Row label="Name" value={user?.full_name || "—"} />
        <Row label="Username" value={user?.username} />
        <Row label="Role" value={user?.role} />
        <Row label="Email" value={user?.email || "—"} />
        <Row label="Last sign-in" value={user?.last_login || "—"} />
      </div>
      <form onSubmit={save} className="card p-5 space-y-3">
        <div className="font-semibold">Change password</div>
        {error && <div className="text-sm text-rose-600">{error}</div>}
        <div>
          <label className="lbl">Current password</label>
          <input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
        </div>
        <div>
          <label className="lbl">New password</label>
          <input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} required />
        </div>
        <div>
          <label className="lbl">Confirm new password</label>
          <input type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} required />
        </div>
        <button className="btn-primary" disabled={busy}>
          {busy ? "Saving…" : "Update password"}
        </button>
      </form>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium capitalize text-right">{value}</span>
    </div>
  );
}
