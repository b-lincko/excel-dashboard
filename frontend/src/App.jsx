import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";
import Layout from "./components/Layout.jsx";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import WorkOrders from "./pages/WorkOrders.jsx";
import WorkOrderDetail from "./pages/WorkOrderDetail.jsx";
import Analytics from "./pages/Analytics.jsx";
import ActionQueue from "./pages/ActionQueue.jsx";
import Suppliers from "./pages/Suppliers.jsx";
import Reports from "./pages/Reports.jsx";
import Settings from "./pages/Settings.jsx";
import AuditLog from "./pages/AuditLog.jsx";
import Users from "./pages/Users.jsx";

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
      <Route
        path="/login"
        element={!loading && user ? <Navigate to="/" replace /> : <Login />}
      />
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
        <Route path="open" element={<WorkOrders presetFlag="open" title="Open Work Orders" />} />
        <Route path="overdue" element={<WorkOrders presetFlag="overdue" title="Overdue Work Orders" />} />
        <Route path="closed" element={<WorkOrders presetFlag="closed" title="Closed Work Orders" />} />
        <Route path="pending" element={<WorkOrders presetFlag="pending" title="Pending Work Orders" />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="queue" element={<ActionQueue />} />
        <Route path="suppliers" element={<Suppliers />} />
        <Route path="reports" element={<Reports />} />
        <Route path="audit" element={<AuditLog />} />
        <Route path="users" element={<Users />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
