import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext.jsx";

export default function Login() {
  const { isAuthenticated, isLoading, login, user } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      await login(username, password);
      navigate("/");
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      setError(detail || "Login failed. Please check your credentials.");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (isLoading) {
    return (
      <section className="flex min-h-[70vh] items-center justify-center">
        <div className="panel w-full max-w-md">
          <p className="text-sm text-slate-300">Checking session...</p>
        </div>
      </section>
    );
  }

  if (isAuthenticated) {
    return (
      <section className="flex min-h-[70vh] items-center justify-center">
        <div className="panel w-full max-w-md">
          <h1 className="text-2xl font-bold text-slate-50">Login</h1>
          <p className="mt-3 text-sm text-slate-300">
            You are signed in as{" "}
            <span className="font-semibold text-cyan-300">{user.username}</span>.
          </p>
          <button
            className="primary-button mt-6 w-full"
            onClick={() => navigate("/")}
            type="button"
          >
            Go to dashboard
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="flex min-h-[70vh] items-center justify-center">
      <div className="panel w-full max-w-md">
        <h1 className="text-2xl font-bold text-slate-50">Login</h1>
        <p className="mt-2 text-sm text-slate-400">
          Sign in to access the Athes Sentinel workspace.
        </p>

        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <label className="block">
            <span className="text-sm font-medium text-slate-300">Username</span>
            <input
              className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-50 outline-none transition focus:border-cyan-400"
              name="username"
              onChange={(event) => setUsername(event.target.value)}
              placeholder="admin"
              type="text"
              value={username}
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-slate-300">Password</span>
            <input
              className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-50 outline-none transition focus:border-cyan-400"
              name="password"
              onChange={(event) => setPassword(event.target.value)}
              placeholder="admin123"
              type="password"
              value={password}
            />
          </label>

          {error ? (
            <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
              {error}
            </div>
          ) : null}

          <p className="text-xs text-slate-500">
            Demo users: admin/admin123 or analyst/analyst123
          </p>

          <button className="primary-button w-full" disabled={isSubmitting} type="submit">
            {isSubmitting ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </div>
    </section>
  );
}
