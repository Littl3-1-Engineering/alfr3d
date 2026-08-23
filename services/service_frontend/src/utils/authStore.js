/**
 * Plain (non-React) token store for ALFR3D auth. Lives outside the React tree because
 * apiClient.js needs to read/refresh the current token from inside a fetch wrapper, not just
 * from components. AuthContext.jsx wraps this in React state for components to consume.
 *
 * Access token: in-memory only (never persisted). Refresh token: sessionStorage (survives a
 * page reload within the tab, cleared on tab/browser close) -- the backend returns the refresh
 * token in the login response body, not an httpOnly cookie, so this is the store's job, not the
 * browser's.
 */
import { API_BASE_URL } from '../config';

const REFRESH_STORAGE_KEY = 'alfr3d-refresh-token';

let accessToken = null;
let refreshToken = null;
try {
  refreshToken = sessionStorage.getItem(REFRESH_STORAGE_KEY);
} catch {
  refreshToken = null;
}

const listeners = new Set();

function notify() {
  for (const cb of listeners) cb();
}

export function subscribe(cb) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function getAccessToken() {
  return accessToken;
}

export function getRefreshToken() {
  return refreshToken;
}

function setTokens(next) {
  accessToken = next?.access_token ?? null;
  refreshToken = next?.refresh_token ?? null;
  try {
    if (refreshToken) {
      sessionStorage.setItem(REFRESH_STORAGE_KEY, refreshToken);
    } else {
      sessionStorage.removeItem(REFRESH_STORAGE_KEY);
    }
  } catch {
    // sessionStorage unavailable (private browsing, etc.) -- token still works in-memory
    // for the rest of this page load, just won't survive a reload.
  }
  notify();
}

function clearTokens() {
  setTokens(null);
}

/** Decode a JWT's payload only -- no signature verification. UI display purposes only; the
 * backend remains the sole authority on whether a token is actually valid. */
export function decodeJwtPayload(token) {
  if (!token) return null;
  try {
    const [, payload] = token.split('.');
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    return JSON.parse(json);
  } catch {
    return null;
  }
}

async function postAuth(path, body) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || 'Request failed');
    error.status = response.status;
    throw error;
  }
  return data;
}

export async function login({ username, password }) {
  const data = await postAuth('/api/auth/login', { username, password });
  setTokens(data);
  return data;
}

export async function claim({ username, password }) {
  const data = await postAuth('/api/auth/claim', { username, password });
  setTokens(data);
  return data;
}

/** Trade the current refresh token for a new access/refresh pair. Returns the new tokens on
 * success, or null (and clears stored state) on failure. */
export async function refresh() {
  if (!refreshToken) return null;
  try {
    const data = await postAuth('/api/auth/refresh', { refresh_token: refreshToken });
    setTokens(data);
    return data;
  } catch {
    clearTokens();
    return null;
  }
}

export async function logout() {
  const currentRefreshToken = refreshToken;
  clearTokens();
  if (currentRefreshToken) {
    try {
      await postAuth('/api/auth/logout', { refresh_token: currentRefreshToken });
    } catch {
      // Best-effort -- local state is already cleared regardless of server-side revoke success.
    }
  }
}
