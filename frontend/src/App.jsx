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
        <Route
          path="analytics"
          element={
            <Suspense fallback={<Fallback />}>
              <Analytics />
            </Suspense>
          }
        />
        <Route
          path="queue"
          element={
            <Suspense fallback={<Fallback />}>
              <ActionQueue />
            </Suspense>
          }
        />
        <Route
          path="suppliers"
          element={
            <Suspense fallback={<Fallback />}>
              <Suppliers />
            </Suspense>
          }
        />
        <Route
          path="reports"
          element={
            <Suspense fallback={<Fallback />}>
              <Reports />
            </Suspense>
          }
        />
        <Route
          path="audit"
          element={
            <Suspense fallback={<Fallback />}>
              <AuditLog />
            </Suspense>
          }
        />
        <Route
          path="users"
          element={
            <Suspense fallback={<Fallback />}>
              <Users />
            </Suspense>
          }
        />
        <Route
          path="settings"
          element={
            <Suspense fallback={<Fallback />}>
              <Settings />
            </Suspense>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
