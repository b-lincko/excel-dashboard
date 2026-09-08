import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useTour } from "../context/TourContext.jsx";
import { useUi } from "../context/UiContext.jsx";

export default function Account() {
  const { user, refresh } = useAuth();
  const { toast } = useUi();
  const { start } = useTour();
  const nav = useNavigate();
  const [fullName, setFullName] = useState(user?.full_name || "");
  const [email, setEmail] = useState(user?.email || "");
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [pwBusy, setPwBusy] = useState(false);
  const [error, setError] = useState("");
  const [pwError, setPwError] = useState("");

  async function saveProfile(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api.put("/api/auth/profile", { full_name: fullName, email });
      await refresh?.();
      toast("Profile updated.", "success");
    } catch (err) {
      setError(err.message || "Could not update profile");
    } finally {
      setBusy(false);
    }
  }

  async function savePassword(e) {
    e.preventDefault();
    setPwError("");
    if (next.length < 8) {
      setPwError("New password must be at least 8 characters.");
      return;
    }
    if (next !== again) {
      setPwError("New passwords do not match.");
      return;
    }
    setPwBusy(true);
    try {
      await api.post("/api/auth/password", { current_password: current, new_password: next });
      setCurrent("");
      setNext("");
      setAgain("");
      toast("Password updated.", "success");
    } catch (err) {
      setPwError(err.message || "Could not update password");
    } finally {
      setPwBusy(false);
    }
  }

  return (
    <div className="space-y-5 max-w-xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Account</h1>
        <p className="text-sm text-slate-500">Your profile, password, and what this login can do.</p>
      </div>
      <div className="card p-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-semibold">New here?</div>
          <p className="text-sm text-slate-500">A short tour of search, the list, a record, and the morning queue.</p>
        </div>
        <div className="flex gap-2">
          <button type="button" className="btn-outline" onClick={() => nav("/guide")}>
            Open guide
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={() => {
              start();
              nav("/");
            }}
          >
            Start tour
          </button>
        </div>
      </div>

      <form onSubmit={saveProfile} className="card p-5 space-y-3">
        <div className="font-semibold">Profile</div>
        {error && <div className="text-sm text-rose-600">{error}</div>}
        <Row label="Username" value={user?.username} />
        <Row label="Role" value={user?.role} />
        <Row label="Last sign-in" value={user?.last_login || "—"} />
        <div>
          <label className="lbl">Full name</label>
          <input value={fullName} onChange={(e) => setFullName(e.target.value)} />
        </div>
        <div>
          <label className="lbl">Email</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <button className="btn-primary" disabled={busy}>
          {busy ? "Saving…" : "Save profile"}
        </button>
      </form>

      <form onSubmit={savePassword} className="card p-5 space-y-3">
        <div className="font-semibold">Change password</div>
        {pwError && <div className="text-sm text-rose-600">{pwError}</div>}
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
        <button className="btn-primary" disabled={pwBusy}>
          {pwBusy ? "Saving…" : "Update password"}
        </button>
      </form>

      <div className="card p-5 space-y-2 text-sm">
        <div className="font-semibold">Your access</div>
        <p className="text-slate-500">
          {(user?.permissions || []).join(", ") || "view"}
        </p>
      </div>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-4 text-sm">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium capitalize text-right">{value}</span>
    </div>
  );
}
