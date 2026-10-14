import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { getCurrentUser, loginUser } from "../api/auth.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadStoredAuth() {
      const storedToken = localStorage.getItem("athes_token");
      const storedUser = localStorage.getItem("athes_user");

      if (!storedToken) {
        setIsLoading(false);
        return;
      }

      setToken(storedToken);

      if (storedUser) {
        try {
          setUser(JSON.parse(storedUser));
        } catch {
          localStorage.removeItem("athes_user");
        }
      }

      try {
        const currentUser = await getCurrentUser();
        localStorage.setItem("athes_user", JSON.stringify(currentUser));
        setUser(currentUser);
      } catch (requestError) {
        // Only discard the session when the server rejects the token. A sleeping
        // or unreachable API (network error, 5xx) must not sign the user out.
        const status = requestError.response?.status;

        if (status === 401 || status === 403) {
          localStorage.removeItem("athes_token");
          localStorage.removeItem("athes_user");
          setToken(null);
          setUser(null);
        }
      } finally {
        setIsLoading(false);
      }
    }

    loadStoredAuth();
  }, []);

  async function login(username, password) {
    const response = await loginUser(username, password);

    localStorage.setItem("athes_token", response.access_token);
    localStorage.setItem("athes_user", JSON.stringify(response.user));
    setToken(response.access_token);
    setUser(response.user);

    return response;
  }

  function logout() {
    localStorage.removeItem("athes_token");
    localStorage.removeItem("athes_user");
    setToken(null);
    setUser(null);
  }

  const value = useMemo(
    () => ({
      user,
      token,
      isAuthenticated: Boolean(token && user),
      isLoading,
      login,
      logout,
    }),
    [user, token, isLoading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }

  return context;
}
