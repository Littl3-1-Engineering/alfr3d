import { useEffect, useRef } from 'react';
import { API_BASE_URL } from '../config';
import { apiFetch } from '../utils/apiClient';
import socket from '../utils/socket';
import { themes } from '../utils/themes';
import { useAuth } from '../utils/useAuth';
import { useTheme } from '../utils/useTheme';

const THEME_URL = `${API_BASE_URL}/api/users/me/theme`;

/**
 * Keeps the signed-in user's theme in step with the backend so the choice carries between the
 * web frontend and alfr3d_deck (todo/todo_theme_sync_deck.md). Last write wins:
 *  - on sign-in, a saved server theme replaces the local one; with none saved, the local one seeds it;
 *  - a local change is PUT to the server;
 *  - a `theme` broadcast for this user (the Deck changed it) is applied live.
 * Renders nothing. Signed-out sessions keep the purely local behaviour.
 */
const ThemeSync = () => {
  const { user, isAuthenticated } = useAuth();
  const { currentTheme, setCurrentTheme } = useTheme();
  // The theme the server is known to hold; null until the first GET resolves (writes wait for it).
  const serverTheme = useRef(null);
  const latestTheme = useRef(currentTheme);
  latestTheme.current = currentTheme;
  const userId = user?.id;

  useEffect(() => {
    if (!isAuthenticated) {
      serverTheme.current = null;
      return undefined;
    }
    let cancelled = false;

    (async () => {
      try {
        const res = await apiFetch(THEME_URL);
        if (!res.ok || cancelled) return;
        const { theme } = await res.json();
        if (cancelled) return;
        if (theme && themes[theme]) {
          serverTheme.current = theme;
          if (theme !== latestTheme.current) setCurrentTheme(theme);
        } else {
          // Nothing saved yet: this device's choice becomes the household default for the user.
          serverTheme.current = latestTheme.current;
          await apiFetch(THEME_URL, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ theme: latestTheme.current }),
          });
        }
      } catch {
        // Offline or older backend without the endpoint: stay local.
      }
    })();

    const onTheme = (data) => {
      if (!data || String(data.user_id) !== String(userId) || !themes[data.theme]) return;
      serverTheme.current = data.theme;
      if (data.theme !== latestTheme.current) setCurrentTheme(data.theme);
    };
    socket.on('theme', onTheme);

    return () => {
      cancelled = true;
      socket.off('theme', onTheme);
    };
  }, [isAuthenticated, userId, setCurrentTheme]);

  useEffect(() => {
    if (!isAuthenticated || serverTheme.current === null) return;
    if (serverTheme.current === currentTheme) return;
    serverTheme.current = currentTheme;
    apiFetch(THEME_URL, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme: currentTheme }),
    }).catch(() => {});
  }, [currentTheme, isAuthenticated]);

  return null;
};

export default ThemeSync;
