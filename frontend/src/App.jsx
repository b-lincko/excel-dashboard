import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { firstPath, useAuth } from "./context/AuthContext.jsx";
import Layout from "./components/Layout.jsx";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import WorkOrders from "./pages/WorkOrders.jsx";
import WorkOrderDetail from "./pages/WorkOrderDetail.jsx";

const Analytics = lazy(() => import("./pages/Analytics.jsx"));
const ActionQueue = lazy(() => import("./pages/ActionQueue.jsx"));
const Alerts = lazy(() => import("./pages/Alerts.jsx"));
const Suppliers = lazy(() => import("./pages/Suppliers.jsx"));
const Reports = lazy(() => import("./pages/Reports.jsx"));
const Settings = lazy(() => import("./pages/Settings.jsx"));
const AuditLog = lazy(() => import("./pages/AuditLog.jsx"));
const Users = lazy(() => import("./pages/Users.jsx"));
const Account = lazy(() => import("./pages/Account.jsx"));
const Performance = lazy(() => import("./pages/Performance.jsx"));
const Chat = lazy(() => import("./pages/Chat.jsx"));
const Projects = lazy(() => import("./pages/Projects.jsx"));
const ImportData = lazy(() => import("./pages/ImportData.jsx"));

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

function Perm({ perm, page, children }) {
  const { can, canPage } = useAuth();
  const allowed = page ? canPage(page) : can(perm);
  if (!allowed) {
    return (
      <div className="card p-8 max-w-md mx-auto text-center">
        <div className="text-lg font-semibold">You don’t have access</div>
        <p className="text-sm text-slate-500 mt-2">
          This page needs the <span className="font-medium">{page || perm}</span> permission. Ask an administrator if you need it.
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

function Lazy({ perm, page, children }) {
  const inner = <Suspense fallback={<Fallback />}>{children}</Suspense>;
  return perm || page ? <Perm perm={perm} page={page}>{inner}</Perm> : inner;
}

export default function App() {
  const { user, loading } = useAuth();
  return (
    <Routes>
      <Route path="/login" element={!loading && user ? <Navigate to={firstPath(user)} replace /> : <Login />} />
      <Route
        path="/"
        element={
          <Guard>
            <Layout />
          </Guard>
        }
      >
        <Route index element={<Perm page="dashboard"><Dashboard /></Perm>} />
        <Route path="work-orders" element={<Perm page="work_orders"><WorkOrders /></Perm>} />
        <Route path="work-orders/new" element={<Perm perm="create"><WorkOrderDetail /></Perm>} />
        <Route path="work-orders/:id" element={<WorkOrderDetail />} />
        <Route path="open" element={<Perm page="open"><WorkOrders presetFlag="open" title="Open work orders" /></Perm>} />
        <Route path="placed" element={<Perm page="placed"><WorkOrders presetFlag="placed" title="Placed work orders" /></Perm>} />
        <Route path="overdue" element={<Perm page="overdue"><WorkOrders presetFlag="overdue" title="Overdue work orders" /></Perm>} />
        <Route path="closed" element={<Perm page="closed"><WorkOrders presetFlag="closed" title="Closed work orders" /></Perm>} />
        <Route path="pending" element={<WorkOrders presetFlag="pending" title="Pending work orders" />} />
        <Route path="analytics" element={<Lazy perm="analytics" page="analytics"><Analytics /></Lazy>} />
        <Route path="queue" element={<Lazy page="queue"><ActionQueue /></Lazy>} />
        <Route path="suppliers" element={<Lazy page="suppliers"><Suppliers /></Lazy>} />
        <Route path="reports" element={<Lazy perm="reports" page="reports"><Reports /></Lazy>} />
        <Route path="audit" element={<Lazy perm="audit"><AuditLog /></Lazy>} />
        <Route path="users" element={<Lazy perm="users"><Users /></Lazy>} />
        <Route path="settings" element={<Lazy perm="settings"><Settings /></Lazy>} />
        <Route path="account" element={<Lazy><Account /></Lazy>} />
        <Route path="performance" element={<Lazy perm="analytics" page="performance"><Performance /></Lazy>} />
        <Route path="chat" element={<Lazy page="chat"><Chat /></Lazy>} />
        <Route path="projects" element={<Lazy page="projects"><Projects /></Lazy>} />
        <Route path="import" element={<Lazy perm="edit" page="import"><ImportData /></Lazy>} />
        <Route path="*" element={<NotFound />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
