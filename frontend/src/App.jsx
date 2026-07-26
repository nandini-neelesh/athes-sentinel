import { Navigate, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import Analytics from "./pages/Analytics.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Incidents from "./pages/Incidents.jsx";
import Login from "./pages/Login.jsx";
import UploadLogs from "./pages/UploadLogs.jsx";
import Workflow from "./pages/Workflow.jsx";
import NetworkAnalytics from "./pages/network/NetworkAnalytics.jsx";
import NetworkIncidents from "./pages/network/NetworkIncidents.jsx";
import NetworkOverview from "./pages/network/NetworkOverview.jsx";
import NetworkUpload from "./pages/network/NetworkUpload.jsx";
import NetworkWorkflow from "./pages/network/NetworkWorkflow.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/upload" element={<UploadLogs />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/incidents" element={<Incidents />} />
          <Route path="/workflow" element={<Workflow />} />
          <Route path="/network" element={<NetworkOverview />} />
          <Route path="/network/upload" element={<NetworkUpload />} />
          <Route path="/network/analytics" element={<NetworkAnalytics />} />
          <Route path="/network/incidents" element={<NetworkIncidents />} />
          <Route path="/network/workflow" element={<NetworkWorkflow />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
