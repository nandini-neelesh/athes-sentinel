import { Outlet } from "react-router-dom";

import Sidebar from "./Sidebar.jsx";

export default function Layout() {
  return (
    <div className="min-h-screen bg-[#0d1516] text-[#dce4e5]">
      <div className="flex min-h-screen">
        <Sidebar />

        <div className="app-canvas min-w-0 flex-1 lg:pl-64">
          <header className="top-shell-bar">
            <div className="flex h-14 items-center justify-between px-5 lg:px-7">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#849396]">
                  <span>Security Operations</span>
                  <span className="text-[#3b494c]">/</span>
                  <span className="text-[#9cf0ff]">Overview</span>
                </div>
                <p className="mt-0.5 truncate text-xs text-[#849396]">
                  Real-time log monitoring and incident triage workspace
                </p>
              </div>

              <div className="status-pill shrink-0">
                <span className="status-dot" aria-hidden="true" />
                System Normal
              </div>
            </div>
          </header>

          <main className="min-h-[calc(100vh-3.5rem)] px-5 py-6 lg:px-7">
            <div className="mx-auto max-w-7xl">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
