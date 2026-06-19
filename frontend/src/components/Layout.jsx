import { Outlet } from "react-router-dom";

import Sidebar from "./Sidebar.jsx";

export default function Layout() {
  return (
    <div className="min-h-screen bg-sentinel-background text-sentinel-text">
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-7xl px-6 py-8 lg:px-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
