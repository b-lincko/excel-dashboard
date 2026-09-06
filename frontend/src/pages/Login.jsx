import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { firstPath, useAuth } from "../context/AuthContext.jsx";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const expired = useMemo(() => {
    const reason = sessionStorage.getItem("woms_auth_reason");
    if (reason === "expired") sessionStorage.removeItem("woms_auth_reason");
    return reason === "expired";
  }, []);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const signedIn = await login(username.trim(), password);
      nav(firstPath(signedIn));
    } catch (err) {
      setError(err.message || "Sign in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      <div className="hidden lg:flex flex-col justify-between bg-ink-900 text-white p-12 relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(34,211,238,0.18),transparent_40%),radial-gradient(circle_at_80%_80%,rgba(14,116,144,0.25),transparent_40%)]" />
        <div className="relative">
          <div className="flex items-center gap-3">
            <div className="h-12 w-12 rounded-2xl bg-gradient-to-br from-cyan-400 to-brand-700 grid place-items-center font-extrabold">
              WO
            </div>
            <div>
              <div className="text-xl font-bold">Linkco MR</div>
              <div className="text-sm text-slate-400">IM Work Order · Material Request log</div>
            </div>
          </div>
        </div>
        <div className="relative max-w-lg">
          <h1 className="text-4xl font-extrabold leading-tight tracking-tight">
            Work orders stay in Excel.
            <span className="block text-cyan-300">The dashboard stays in sync.</span>
          </h1>
          <p className="mt-5 text-slate-300 text-sm leading-relaxed">
            Read, edit and report on the live workbook. Every save writes back to the source file,
            with backups, audit history and conflict detection.
          </p>
        </div>
        <div className="relative text-xs text-slate-500">Work Order Management System · Source of truth: Excel</div>
      </div>
      <div className="grid place-items-center p-8 bg-slate-50 dark:bg-ink-900">
        <form onSubmit={submit} className="w-full max-w-sm card p-8">
          <h2 className="text-xl font-bold">Sign in</h2>
          <p className="text-sm text-slate-500 mt-1 mb-6">Use your WOMS account to continue.</p>
          {expired && !error && (
            <div className="mb-4 rounded-lg bg-amber-50 text-amber-800 text-sm px-3 py-2 dark:bg-amber-500/10 dark:text-amber-200">
              Your session expired. Sign in again to continue.
            </div>
          )}
          {error && (
            <div className="mb-4 rounded-lg bg-rose-50 text-rose-700 text-sm px-3 py-2 dark:bg-rose-500/10 dark:text-rose-300">
              {error}
              {String(error).includes("API is not running") && (
                <div className="mt-2 text-xs">
                  run.bat must open two windows: <b>Linkco MR API</b> and <b>Linkco MR UI</b>.
                  If the API window closed, run <code>scripts\\start-api.bat</code> and leave it open.
                </div>
              )}
            </div>
          )}
          <label className="lbl">Username</label>
          <input
            className="mb-3"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            autoComplete="username"
            name="username"
            required
          />
          <label className="lbl">Password</label>
          <input
            className="mb-5"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            name="password"
            required
          />
          <button className="btn-primary w-full" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
          <div className="mt-6 text-xs text-slate-500 space-y-1">
            <div className="font-semibold text-slate-600 dark:text-slate-300">Built-in accounts</div>
            <div>admin / admin123 — full access</div>
            <div>manager / manager123 — edit & reports</div>
            <div>user / user123 — view & update</div>
          </div>
        </form>
      </div>
    </div>
  );
}
