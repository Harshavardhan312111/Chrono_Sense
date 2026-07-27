import { createContext, useContext, useEffect, useState } from "react";
import {
  clearStoredAuth,
  getStoredToken,
  getStoredUser,
  loginRequest,
  logoutRequest,
  persistAuthSession,
  verifyRequest
} from "../lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(getStoredUser());
  const [token, setToken] = useState(getStoredToken());
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    async function restoreSession() {
      const existingToken = getStoredToken();

      if (!existingToken) {
        setIsReady(true);
        return;
      }

      try {
        const verifiedUser = await verifyRequest();
        setUser(verifiedUser);
        setToken(existingToken);
      } catch {
        clearStoredAuth();
        setUser(null);
        setToken(null);
      } finally {
        setIsReady(true);
      }
    }

    restoreSession();
  }, []);

    async function login(credentials) {
    const result = await loginRequest(credentials);
    const nextUser = {
      user_id: result.user_id,
      username: result.username,
      role: result.role,
      role_label: result.role_label,
      capabilities: result.capabilities || [],
      scope: result.scope || {},
      first_name: result.first_name,
      last_name: result.last_name
    };

    persistAuthSession({
      token: result.token,
      user: nextUser,
      rememberMe: credentials.rememberMe
    });

    setUser(nextUser);
    setToken(result.token);
    return nextUser;
  }

  async function logout() {
    try {
      if (getStoredToken()) {
        await logoutRequest();
      }
    } catch {
      // Clear local auth state even if the server-side session is already gone.
    } finally {
      clearStoredAuth();
      setUser(null);
      setToken(null);
    }
  }

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated: Boolean(user && token),
        isReady,
        login,
        logout,
        token,
        user
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }

  return context;
}
