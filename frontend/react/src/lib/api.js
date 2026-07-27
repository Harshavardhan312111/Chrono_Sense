const AUTH_TOKEN_KEY = "auth_token";
const CURRENT_USER_KEY = "current_user";

function getStoredValue(key) {
  return localStorage.getItem(key) || sessionStorage.getItem(key);
}

export function getStoredToken() {
  return getStoredValue(AUTH_TOKEN_KEY);
}

export function getStoredUser() {
  const rawUser = getStoredValue(CURRENT_USER_KEY);

  if (!rawUser) {
    return null;
  }

  try {
    return JSON.parse(rawUser);
  } catch {
    return null;
  }
}

export function clearStoredAuth() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(CURRENT_USER_KEY);
  sessionStorage.removeItem(AUTH_TOKEN_KEY);
  sessionStorage.removeItem(CURRENT_USER_KEY);
}

export function persistAuthSession({ token, user, rememberMe }) {
  clearStoredAuth();

  const storage = rememberMe ? localStorage : sessionStorage;
  storage.setItem(AUTH_TOKEN_KEY, token);
  storage.setItem(CURRENT_USER_KEY, JSON.stringify(user));
}

export async function apiRequest(path, options = {}) {
  const token = getStoredToken();
  const headers = new Headers(options.headers || {});

  if (!headers.has("Content-Type") && options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(path, {
    ...options,
    headers
  });

  const isJson = response.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const message =
      typeof payload === "object" && (payload?.detail || payload?.error)
        ? (payload.detail || payload.error)
        : "Request failed";
    const error = new Error(message);
    if (typeof payload === "object" && payload) {
      error.payload = payload;
      if (payload.view_errors) {
        error.view_errors = payload.view_errors;
      }
    }
    throw error;
  }

  return payload;
}

export async function loginRequest(credentials) {
  return apiRequest("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(credentials)
  });
}

export async function verifyRequest() {
  return apiRequest("/api/auth/verify");
}

export async function logoutRequest() {
  return apiRequest("/api/auth/logout", {
    method: "POST"
  });
}
