import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import { AppLayout } from "./components/AppLayout";
import { Spinner } from "./components/ui";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import Predictions from "./pages/Predictions";
import History from "./pages/History";
import Draws from "./pages/Draws";
import Profile from "./pages/Profile";
import Earnings from "./pages/Earnings";
import AdminUsers from "./pages/AdminUsers";
import Analytics from "./pages/Analytics";
import AssistantChat from "./pages/AssistantChat";
import Legal from "./pages/Legal";
import ResetPassword from "./pages/ResetPassword";

function Protected({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading)
    return (
      <div className="min-h-screen flex items-center justify-center bg-aurora">
        <Spinner label="Cargando MelateAI Pro…" />
      </div>
    );
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  return <AppLayout>{children}</AppLayout>;
}

export default function App() {
  const { user, loading } = useAuth();

  return (
    <Routes>
      <Route path="/login" element={user && !loading ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/register" element={user && !loading ? <Navigate to="/" replace /> : <Register />} />
      <Route path="/reset" element={<ResetPassword />} />
      <Route path="/" element={<Protected><Dashboard /></Protected>} />
      <Route path="/predicciones" element={<Protected><Predictions /></Protected>} />
      <Route path="/historial" element={<Protected><History /></Protected>} />
      <Route path="/sorteos" element={<Protected><Draws /></Protected>} />
      <Route path="/estimador" element={<Protected><Earnings /></Protected>} />
      <Route path="/rendimiento" element={<Protected><Analytics /></Protected>} />
      <Route path="/asistente" element={<Protected><AssistantChat /></Protected>} />
      <Route path="/responsable" element={<Protected><Legal /></Protected>} />
      <Route path="/perfil" element={<Protected><Profile /></Protected>} />
      <Route path="/admin/usuarios" element={<Protected><AdminUsers /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
