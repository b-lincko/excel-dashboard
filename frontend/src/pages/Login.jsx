import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { firstPath, useAuth } from "../context/AuthContext.jsx";
import LoginScene from "../components/LoginScene.jsx";

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
      nav(signedIn?.must_change_password ? "/account" : firstPath(signedIn));
    } catch (err) {
      const timedOut = err?.timeout || String(err.message || "").toLowerCase().includes("timed out");
      setError(
        timedOut
          ? "Sign-in timed out. If you just uploaded Excel, wait until that finishes, then try again."
          : err.message || "Sign in failed"
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      <div className="hidden lg:flex flex-col justify-between bg-brand-700 text-white p-12 relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(255,255,255,0.12),transparent_40%),radial-gradient(circle_at_80%_80%,rgba(8,94,82,0.45),transparent_40%)]" />
        <LoginScene />
        <div className="relative z-10">
          <div className="flex items-center gap-3">
            <div className="h-12 w-12 rounded-2xl bg-white text-brand-700 grid place-items-center font-extrabold">
              WO
            </div>
            <div>
              <div className="text-xl font-bold">Linkco MR</div>
              <div className="text-sm text-white/70">Work orders · Material requests</div>
            </div>
          </div>
        </div>
        <div className="relative z-10 max-w-lg">
          <h1 className="text-4xl font-extrabold leading-tight tracking-tight">
            Material requests in one place.
            <span className="block text-white/90">Act on what is late, blocked, or due.</span>
          </h1>
          <p className="mt-5 text-white/75 text-sm leading-relaxed">
            The database is the live history. Excel is a midnight replica. Claim, follow, and close MRs without hunting through the workbook.
          </p>
        </div>
        <div className="relative z-10 text-xs text-white/50">Linkco MR · Work order management</div>
      </div>
      <div className="grid place-items-center p-8 bg-slate-50 dark:bg-ink-900">
        <form onSubmit={submit} className="w-full max-w-sm card p-8">
          <h2 className="text-xl font-bold">Sign in</h2>
          <p className="text-sm text-slate-500 mt-1 mb-6">Use your WOMS account. First sign-in starts a short tour.</p>
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
        </form>
      </div>
    </div>
  );
}
