/**
 * Plain (non-React) token store for ALFR3D auth. Lives outside the React tree because
 * apiClient.js needs to read/refresh the current token from inside a fetch wrapper, not just
 * from components. AuthContext.jsx wraps this in React state for components to consume.
 *
 * Access token: in-memory only (never persisted). Refresh token: localStorage (survives reloads,
 * tab/browser close and restarts, and is shared across tabs) -- the backend returns the refresh
 * token in the login response body, not an httpOnly cookie, so this is the store's job, not the
 * browser's.
 *
 * Staying logged in on an always-open tab: the access token is refreshed proactively shortly
 * before it expires (and on tab-visible / back-online), and a refresh only wipes the session when
 * the server explicitly rejects the token (401/403) -- a network blip or 5xx keeps the tokens and
 * retries with backoff. The refresh token is single-use, so cross-tab refreshes are serialized
 * with a Web Lock and always redeem the latest token from localStorage.
 */
import { API_BASE_URL } from '../config';

const REFRESH_STORAGE_KEY = 'alfr3d-refresh-token';

const REFRESH_LEAD_SECONDS = 60;
const RETRY_BASE_MS = 15_000;
const RETRY_MAX_MS = 5 * 60_000;
const LOCK_NAME = 'alfr3d-auth-refresh';

function readStoredRefreshToken() {
  try {
    const current = localStorage.getItem(REFRESH_STORAGE_KEY);
    if (current) return current;
    // One-time migration from the old per-tab sessionStorage location.
    const legacy = sessionStorage.getItem(REFRESH_STORAGE_KEY);
    if (legacy) {
      localStorage.setItem(REFRESH_STORAGE_KEY, legacy);
      sessionStorage.removeItem(REFRESH_STORAGE_KEY);
    }
    return legacy;
  } catch {
    return null;
  }
}

let accessToken = null;
let refreshToken = readStoredRefreshToken();
let refreshTimer = null;
let retryAttempt = 0;

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
      localStorage.setItem(REFRESH_STORAGE_KEY, refreshToken);
    } else {
      localStorage.removeItem(REFRESH_STORAGE_KEY);
    }
  } catch {
    // localStorage unavailable (private browsing, etc.) -- token still works in-memory
    // for the rest of this page load, just won't survive a reload.
  }
  scheduleRefresh();
  notify();
}

function clearTokens() {
  clearRefreshTimer();
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

export async function bootstrap({ username, password }) {
  const data = await postAuth('/api/auth/bootstrap', { username, password });
  setTokens(data);
  return data;
}

/** Unauthenticated system-state check -- tells the app whether to show first-run onboarding
 * instead of the normal sign-in flow. See services/service_api/auth/routes.py's setup_status. */
export async function getSetupStatus() {
  const response = await fetch(`${API_BASE_URL}/api/auth/setup-status`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || 'Request failed');
    error.status = response.status;
    throw error;
  }
  return data;
}

let refreshInFlight = null;

function clearRefreshTimer() {
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
}

/** (Re)arm the proactive refresh for ~REFRESH_LEAD_SECONDS before the access token expires. */
function scheduleRefresh(delayMs) {
  clearRefreshTimer();
  if (!refreshToken) return;
  let delay = delayMs;
  if (delay === undefined) {
    const exp = decodeJwtPayload(accessToken)?.exp;
    if (!exp) return;
    delay = Math.max(5_000, (exp - REFRESH_LEAD_SECONDS) * 1000 - Date.now());
  }
  refreshTimer = setTimeout(() => {
    refreshTimer = null;
    refresh();
  }, delay);
}

function accessTokenNeedsRefresh() {
  if (!accessToken) return true;
  const exp = decodeJwtPayload(accessToken)?.exp;
  return !!exp && exp * 1000 - Date.now() < REFRESH_LEAD_SECONDS * 1000;
}

async function redeemRefreshToken() {
  // Another tab may have rotated the single-use token since we last looked; always redeem the
  // newest one. If it also already produced a fresh pair there, adopt it without a request.
  const stored = readStoredRefreshToken();
  if (stored && stored !== refreshToken) refreshToken = stored;
  if (!refreshToken) return null;

  try {
    const data = await postAuth('/api/auth/refresh', { refresh_token: refreshToken });
    retryAttempt = 0;
    setTokens(data);
    return data;
  } catch (error) {
    if (error.status === 401 || error.status === 403) {
      // The server explicitly rejected the token -- the session is genuinely over.
      retryAttempt = 0;
      clearTokens();
      return null;
    }
    // Network error / 5xx / anything transient: keep the tokens and try again with backoff.
    const backoff = Math.min(RETRY_BASE_MS * 2 ** retryAttempt, RETRY_MAX_MS);
    retryAttempt += 1;
    scheduleRefresh(backoff);
    return null;
  }
}

/** Trade the current refresh token for a new access/refresh pair. Returns the new tokens on
 * success, or null on failure. Stored state is cleared only when the server rejects the refresh
 * token; transient failures keep it and schedule a retry.
 *
 * The refresh token is single-use (the backend revokes it on redemption), so if two callers
 * race in here with the same token, whichever request loses the race gets a 401 and would
 * otherwise clear out the tokens the winner just set. Sharing one in-flight promise across
 * concurrent callers avoids that within a tab, and a Web Lock serializes it across tabs. */
export function refresh() {
  if (refreshInFlight) return refreshInFlight;
  if (!refreshToken && !readStoredRefreshToken()) return Promise.resolve(null);

  const run = () => redeemRefreshToken();
  const locked =
    typeof navigator !== 'undefined' && navigator.locks?.request
      ? navigator.locks.request(LOCK_NAME, run)
      : run();

  refreshInFlight = Promise.resolve(locked).finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

function refreshIfNeeded() {
  if (refreshToken && accessTokenNeedsRefresh()) refresh();
}

if (typeof window !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') refreshIfNeeded();
  });
  window.addEventListener('online', refreshIfNeeded);
  // Another tab logged in / rotated / logged out: follow its refresh token.
  window.addEventListener('storage', (event) => {
    if (event.key !== REFRESH_STORAGE_KEY) return;
    const next = event.newValue;
    if (next === refreshToken) return;
    refreshToken = next;
    if (!next) accessToken = null;
    if (next) scheduleRefresh();
    else clearRefreshTimer();
    notify();
  });
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
