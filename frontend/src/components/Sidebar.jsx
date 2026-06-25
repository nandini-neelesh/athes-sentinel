import {
  Activity,
  BarChart3,
  ClipboardList,
  FileUp,
  LayoutDashboard,
  LogIn,
  ShieldCheck,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { useAuth } from "../context/AuthContext.jsx";

const navItems = [
  { label: "Overview", path: "/", icon: LayoutDashboard },
  { label: "Upload Logs", path: "/upload", icon: FileUp },
  { label: "Analytics", path: "/analytics", icon: BarChart3 },
  { label: "Incidents", path: "/incidents", icon: Activity },
  { label: "Workflow", path: "/workflow", icon: ClipboardList },
  { label: "Login", path: "/login", icon: LogIn },
];

export default function Sidebar() {
  const { isAuthenticated, logout, user } = useAuth();

  return (
    <aside className="fixed left-0 top-0 z-40 hidden h-screen w-64 shrink-0 border-r border-[#3b494c] bg-[#0d1516] px-4 py-5 lg:flex lg:flex-col">
      <div>
        <div className="mb-8 flex items-center gap-3 px-2">
          <div className="flex h-8 w-8 items-center justify-center rounded bg-[#00e5ff] text-[#00363d]">
            <ShieldCheck className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <p className="text-lg font-bold leading-tight text-[#c3f5ff]">
              Athes Sentinel
            </p>
            <p className="mt-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-[#849396]">
              SOC Command Center
            </p>
          </div>
        </div>

        <nav className="space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;

            return (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === "/"}
                className={({ isActive }) =>
                  [
                    "flex items-center gap-3 rounded px-3 py-2.5 text-sm font-medium transition",
                    isActive
                      ? "border-r-2 border-[#9cf0ff] bg-[#242b2d] text-[#c3f5ff]"
                      : "text-[#bac9cc] hover:bg-[#192122] hover:text-[#c3f5ff]",
                  ].join(" ")
                }
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                {item.label}
              </NavLink>
            );
          })}
        </nav>
      </div>

      <div className="mt-auto border-t border-[#3b494c] pt-4">
        {isAuthenticated ? (
          <>
            <p className="text-sm font-semibold text-[#dce4e5]">{user.username}</p>
            <p className="mt-1 text-[11px] uppercase tracking-[0.16em] text-[#9cf0ff]">
              {user.role}
            </p>
            <button
              className="mt-4 w-full rounded border border-[#3b494c] px-3 py-2 text-sm font-semibold text-[#bac9cc] transition hover:border-[#00daf3] hover:text-[#c3f5ff]"
              onClick={logout}
              type="button"
            >
              Logout
            </button>
          </>
        ) : (
          <p className="text-sm text-[#849396]">Not signed in</p>
        )}
      </div>
    </aside>
  );
}
