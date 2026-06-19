import {
  Activity,
  BarChart3,
  ClipboardList,
  FileUp,
  LayoutDashboard,
  LogIn,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { useAuth } from "../context/AuthContext.jsx";

const navItems = [
  { label: "Dashboard", path: "/", icon: LayoutDashboard },
  { label: "Upload Logs", path: "/upload", icon: FileUp },
  { label: "Analytics", path: "/analytics", icon: BarChart3 },
  { label: "Incidents", path: "/incidents", icon: Activity },
  { label: "Workflow", path: "/workflow", icon: ClipboardList },
  { label: "Login", path: "/login", icon: LogIn },
];

export default function Sidebar() {
  const { isAuthenticated, logout, user } = useAuth();

  return (
    <aside className="hidden w-72 shrink-0 border-r border-slate-700 bg-slate-900/80 px-4 py-6 lg:flex lg:flex-col">
      <div>
        <div className="mb-8 rounded-lg border border-slate-700 bg-slate-800 p-4">
          <p className="text-lg font-bold text-slate-50">Athes Sentinel</p>
          <p className="mt-1 text-xs text-slate-400">Lightweight SIEM workspace</p>
        </div>

        <nav className="space-y-2">
          {navItems.map((item) => {
            const Icon = item.icon;

            return (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === "/"}
                className={({ isActive }) =>
                  [
                    "flex items-center gap-3 rounded-lg border px-3 py-2.5 text-sm font-medium transition",
                    isActive
                      ? "border-cyan-400/60 bg-cyan-400/10 text-cyan-300"
                      : "border-transparent text-slate-400 hover:border-slate-700 hover:bg-slate-800 hover:text-slate-100",
                  ].join(" ")
                }
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            );
          })}
        </nav>
      </div>

      <div className="mt-auto rounded-lg border border-slate-700 bg-slate-800 p-4">
        {isAuthenticated ? (
          <>
            <p className="text-sm font-semibold text-slate-50">{user.username}</p>
            <p className="mt-1 text-xs uppercase tracking-wide text-cyan-300">
              {user.role}
            </p>
            <button
              className="mt-4 w-full rounded-lg border border-slate-600 px-3 py-2 text-sm font-semibold text-slate-200 transition hover:border-cyan-400 hover:text-cyan-300"
              onClick={logout}
              type="button"
            >
              Logout
            </button>
          </>
        ) : (
          <p className="text-sm text-slate-400">Not signed in</p>
        )}
      </div>
    </aside>
  );
}
