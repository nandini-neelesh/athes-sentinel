import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "../context/AuthContext.jsx";

export default function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0d1516] px-6 text-[#bac9cc]">
        <div className="rounded-md border border-[#3b494c] bg-[#192122]/90 px-5 py-4 shadow-lg shadow-black/20">
          <p className="text-sm font-semibold tracking-wide">
            Checking secure session...
          </p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
