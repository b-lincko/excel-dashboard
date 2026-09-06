import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";
import Layout from "./components/Layout.jsx";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import WorkOrders from "./pages/WorkOrders.jsx";
import WorkOrderDetail from "./pages/WorkOrderDetail.jsx";

const Analytics = lazy(() => import("./pages/Analytics.jsx"));
const ActionQueue = lazy(() => import("./pages/ActionQueue.jsx"));
const Suppliers = lazy(() => import("./pages/Suppliers.jsx"));
const Reports = lazy(() => import("./pages/Reports.jsx"));
const Settings = lazy(() => import("./pages/Settings.jsx"));
const AuditLog = lazy(() => import("./pages/AuditLog.jsx"));
const Users = lazy(() => import("./pages/Users.jsx"));
const Account = lazy(() => import("./pages/Account.jsx"));

function Fallback() {
  return <div className="text-sm text-slate-500 py-10 text-center">Loading…</div>;
}

function Guard({ children }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen grid place-items-center bg-slate-50 dark:bg-ink-900">
        <div className="text-sm text-slate-500">Loading workspace…</div>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function Perm({ perm, children }) {
  const { can } = useAuth();
  if (!can(perm)) {
    return (
      <div className="card p-8 max-w-md mx-auto text-center">
        <div className="text-lg font-semibold">You don’t have access</div>
        <p className="text-sm text-slate-500 mt-2">
          This page needs the <span className="font-medium">{perm}</span> permission. Ask an administrator if you need it.
        </p>
      </div>
    );
  }
  return children;
}

function NotFound() {
  return (
    <div className="card p-8 max-w-md mx-auto text-center">
      <div className="text-lg font-semibold">Page not found</div>
      <p className="text-sm text-slate-500 mt-2">That URL is not part of Linkco MR.</p>
      <a className="btn-primary mt-4 inline-flex" href="/">
        Back to dashboard
      </a>
    </div>
  );
}

function Lazy({ perm, children }) {
  const inner = <Suspense fallback={<Fallback />}>{children}</Suspense>;
  return perm ? <Perm perm={perm}>{inner}</Perm> : inner;
}

export default function App() {
  const { user, loading } = useAuth();
  return (
    <Routes>
      <Route path="/login" element={!loading && user ? <Navigate to="/" replace /> : <Login />} />
      <Route
        path="/"
        element={
          <Guard>
            <Layout />
          </Guard>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="work-orders" element={<WorkOrders />} />
        <Route path="work-orders/new" element={<WorkOrderDetail />} />
        <Route path="work-orders/:id" element={<WorkOrderDetail />} />
        <Route path="open" element={<WorkOrders presetFlag="open" title="Open work orders" />} />
        <Route path="overdue" element={<WorkOrders presetFlag="overdue" title="Overdue work orders" />} />
        <Route path="closed" element={<WorkOrders presetFlag="closed" title="Closed work orders" />} />
        <Route path="pending" element={<WorkOrders presetFlag="pending" title="Pending work orders" />} />
        <Route path="analytics" element={<Lazy perm="analytics"><Analytics /></Lazy>} />
        <Route path="queue" element={<Lazy><ActionQueue /></Lazy>} />
        <Route path="suppliers" element={<Lazy><Suppliers /></Lazy>} />
        <Route path="reports" element={<Lazy perm="reports"><Reports /></Lazy>} />
        <Route path="audit" element={<Lazy perm="audit"><AuditLog /></Lazy>} />
        <Route path="users" element={<Lazy perm="users"><Users /></Lazy>} />
        <Route path="settings" element={<Lazy perm="settings"><Settings /></Lazy>} />
        <Route path="account" element={<Lazy><Account /></Lazy>} />
        <Route path="*" element={<NotFound />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
