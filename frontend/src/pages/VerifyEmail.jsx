import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api.js";
import BrandLogo from "../components/BrandLogo.jsx";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [state, setState] = useState(token ? "working" : "missing");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return undefined;
    let cancelled = false;
    api
      .post("/api/auth/verify-email", { token })
      .then(() => {
        if (!cancelled) setState("ok");
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e.message || "This link is invalid or has expired.");
        setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <div className="min-h-screen grid place-items-center bg-slate-50 dark:bg-ink-900 p-6">
      <div className="card p-8 max-w-md w-full space-y-4 text-center">
        <BrandLogo className="h-10 w-auto max-w-[160px] mx-auto object-contain" />
        <h1 className="text-xl font-bold">Verify email</h1>
        {state === "working" && <p className="text-sm text-slate-500">Confirming this address…</p>}
        {state === "ok" && (
          <p className="text-sm text-emerald-700 dark:text-emerald-300">Email confirmed. You can sign in and receive PO and request emails.</p>
        )}
        {state === "missing" && <p className="text-sm text-slate-500">This page needs a link from your email.</p>}
        {state === "error" && <p className="text-sm text-rose-600">{error}</p>}
        <Link className="btn-primary inline-flex" to="/login">
          Sign in
        </Link>
      </div>
    </div>
  );
}
