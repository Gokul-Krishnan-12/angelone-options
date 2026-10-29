/**
 * Centralized authenticated fetch utility for Angel One Options Sniper SPA.
 * Automatically injects Bearer token from localStorage and credentials: 'include'.
 */
export const authFetch = (url, options = {}) => {
  const token = localStorage.getItem('sniper_session_token');
  const headers = {
    ...(options.headers || {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {})
  };
  return fetch(url, {
    ...options,
    credentials: 'include',
    headers
  });
};

export default authFetch;
