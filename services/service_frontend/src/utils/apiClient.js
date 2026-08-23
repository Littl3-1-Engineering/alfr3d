/**
 * Drop-in replacement for `fetch()` that injects the bearer access token and, on a 401,
 * transparently refreshes it once and retries. Every write call site in the app should import
 * `apiFetch` in place of the global `fetch` -- same signature (full URL string + fetch options),
 * so the migration is a pure rename.
 */
import * as authStore from './authStore';

export async function apiFetch(url, options = {}) {
  return doFetch(url, options, /* isRetry */ false);
}

async function doFetch(url, options, isRetry) {
  const token = authStore.getAccessToken();
  const headers = { ...options.headers };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(url, { ...options, headers });

  if (response.status === 401 && !isRetry && authStore.getRefreshToken()) {
    const refreshed = await authStore.refresh();
    if (refreshed) {
      return doFetch(url, options, /* isRetry */ true);
    }
  }

  return response;
}
