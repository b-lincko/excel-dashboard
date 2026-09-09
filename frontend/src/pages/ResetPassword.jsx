import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api.js";
import BrandLogo from "../components/BrandLogo.jsx";

export default function ResetPassword() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== again) {
      setError("Passwords do not match.");
      return;
    }
    if (!token) {
      setError("This page needs a link from your email.");
      return;
    }
    setBusy(true);
    try {
      await api.post("/api/auth/reset-password", { token, new_password: password });
      nav("/login");
    } catch (err) {
      setError(err.message || "Could not reset the password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen grid place-items-center bg-slate-50 dark:bg-ink-900 p-6">
      <form onSubmit={submit} className="card p-8 max-w-md w-full space-y-3">
        <BrandLogo className="h-10 w-auto max-w-[160px] mx-auto object-contain" />
        <h1 className="text-xl font-bold text-center">Choose a new password</h1>
        {error && <div className="text-sm text-rose-600">{error}</div>}
        <div>
          <label className="lbl">New password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required />
        </div>
        <div>
          <label className="lbl">Confirm</label>
          <input type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
        </div>
        <button className="btn-primary w-full" disabled={busy}>
          {busy ? "Saving…" : "Update password"}
        </button>
        <Link className="block text-center text-sm text-brand-700 dark:text-cyan-300" to="/login">
          Back to sign in
        </Link>
      </form>
    </div>
  );
}
