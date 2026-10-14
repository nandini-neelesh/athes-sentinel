import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { AlertTriangle, Eye, EyeOff, Loader2, ShieldCheck } from "lucide-react";

import { apiConfigError } from "../api/client.js";
import { useAuth } from "../context/AuthContext.jsx";

const SLOW_RESPONSE_MS = 6000;

function describeLoginError(requestError) {
  if (requestError.response) {
    const detail = requestError.response.data?.detail;

    if (requestError.response.status === 401) {
      return "Incorrect username or password.";
    }

    if (typeof detail === "string") {
      return detail;
    }

    return "Sign-in failed. Please try again.";
  }

  if (requestError.message === apiConfigError) {
    return apiConfigError;
  }

  return "Cannot reach the server. Check your connection and try again in a moment.";
}

export default function Login() {
  const { isAuthenticated, isLoading, login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSlow, setIsSlow] = useState(false);

  // Free hosting tiers put the API to sleep; tell the user why the first
  // sign-in is slow instead of leaving the button spinning without context.
  useEffect(() => {
    if (!isSubmitting) {
      setIsSlow(false);
      return undefined;
    }

    const timer = setTimeout(() => setIsSlow(true), SLOW_RESPONSE_MS);
    return () => clearTimeout(timer);
  }, [isSubmitting]);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      await login(username.trim(), password);
      navigate("/", { replace: true });
    } catch (requestError) {
      setError(describeLoginError(requestError));
    } finally {
      setIsSubmitting(false);
    }
  }

  if (isLoading) {
    return (
      <div className="app-canvas flex min-h-screen items-center justify-center px-6">
        <p className="text-sm text-[#bac9cc]">Checking secure session...</p>
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  const canSubmit = username.trim() && password && !isSubmitting && !apiConfigError;

  return (
    <div className="app-canvas flex min-h-screen items-center justify-center px-5 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-lg border border-[#00e5ff]/30 bg-[#00e5ff]/10 text-[#00e5ff]">
            <ShieldCheck aria-hidden="true" size={26} />
          </div>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight text-[#dce4e5]">
            Athes Sentinel
          </h1>
          <p className="mt-1 text-sm text-[#bac9cc]">
            Security monitoring and incident triage
          </p>
        </div>

        <div className="panel">
          <h2 className="text-base font-semibold text-[#dce4e5]">Sign in</h2>

          <form className="mt-5 space-y-4" onSubmit={handleSubmit}>
            <label className="block">
              <span className="muted-label">Username</span>
              <input
                autoCapitalize="none"
                autoComplete="username"
                autoCorrect="off"
                className="mt-2 w-full rounded border border-[#3b494c] bg-[#0d1516] px-3 py-2 text-sm text-[#dce4e5] outline-none transition focus:border-[#00e5ff]"
                name="username"
                onChange={(event) => setUsername(event.target.value)}
                required
                spellCheck={false}
                type="text"
                value={username}
              />
            </label>

            <label className="block">
              <span className="muted-label">Password</span>
              <div className="relative mt-2">
                <input
                  autoComplete="current-password"
                  className="w-full rounded border border-[#3b494c] bg-[#0d1516] py-2 pl-3 pr-10 text-sm text-[#dce4e5] outline-none transition focus:border-[#00e5ff]"
                  name="password"
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  type={showPassword ? "text" : "password"}
                  value={password}
                />
                <button
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-[#849396] transition hover:text-[#dce4e5]"
                  onClick={() => setShowPassword((visible) => !visible)}
                  tabIndex={-1}
                  type="button"
                >
                  {showPassword ? (
                    <EyeOff aria-hidden="true" size={16} />
                  ) : (
                    <Eye aria-hidden="true" size={16} />
                  )}
                </button>
              </div>
            </label>

            {apiConfigError || error ? (
              <div
                className="flex items-start gap-2 rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200"
                role="alert"
              >
                <AlertTriangle
                  aria-hidden="true"
                  className="mt-0.5 shrink-0"
                  size={15}
                />
                <span>{apiConfigError || error}</span>
              </div>
            ) : null}

            <button
              className="primary-button flex w-full items-center justify-center gap-2 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={!canSubmit}
              type="submit"
            >
              {isSubmitting ? (
                <>
                  <Loader2 aria-hidden="true" className="animate-spin" size={16} />
                  Signing in...
                </>
              ) : (
                "Sign in"
              )}
            </button>

            {isSlow ? (
              <p className="text-center text-xs text-[#849396]" role="status">
                The server is waking up after a period of inactivity. This can
                take up to a minute.
              </p>
            ) : null}
          </form>
        </div>

        <p className="mt-6 text-center text-xs text-[#849396]">
          Authorized users only.
        </p>
      </div>
    </div>
  );
}
