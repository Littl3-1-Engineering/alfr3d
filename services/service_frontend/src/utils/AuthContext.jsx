import { createContext, useEffect, useState, useCallback } from 'react';
import PropTypes from 'prop-types';
import * as authStore from './authStore';

const AuthContext = createContext();

function deriveUser(accessToken) {
  const payload = authStore.decodeJwtPayload(accessToken);
  if (!payload) return null;
  return { id: payload.sub, role: payload.type, exp: payload.exp };
}

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(() => deriveUser(authStore.getAccessToken()));

  useEffect(() => {
    const syncFromStore = () => setUser(deriveUser(authStore.getAccessToken()));
    const unsubscribe = authStore.subscribe(syncFromStore);

    // On mount, an access token never survives a reload (in-memory only) but the refresh
    // token does (sessionStorage) -- attempt a silent resume so a reload doesn't force a
    // fresh login mid-session.
    if (!authStore.getAccessToken() && authStore.getRefreshToken()) {
      authStore.refresh();
    }

    return unsubscribe;
  }, []);

  const login = useCallback((username, password) => authStore.login({ username, password }), []);
  const claim = useCallback((username, password) => authStore.claim({ username, password }), []);
  const bootstrap = useCallback(
    (username, password) => authStore.bootstrap({ username, password }),
    []
  );
  const logout = useCallback(() => authStore.logout(), []);

  const value = {
    user,
    isAuthenticated: user !== null,
    login,
    claim,
    bootstrap,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

AuthProvider.propTypes = {
  children: PropTypes.node.isRequired,
};

export default AuthContext;
