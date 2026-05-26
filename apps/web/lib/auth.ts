const TOKEN_KEY = 'odontoflux_access_token';
const REFRESH_TOKEN_KEY = 'odontoflux_refresh_token';
const ADM_TOKEN_KEY = 'odontoflux_adm_access_token';
const ADM_REFRESH_TOKEN_KEY = 'odontoflux_adm_refresh_token';

type TokenPayload = {
  exp?: number;
  roles?: string[];
};

function parseTokenPayload(token: string | null): TokenPayload | null {
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length < 2) return null;
  try {
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const json = window.atob(base64);
    return JSON.parse(json) as TokenPayload;
  } catch {
    return null;
  }
}

function isExpiredToken(token: string | null) {
  const payload = parseTokenPayload(token);
  if (!payload?.exp) return false;
  return payload.exp * 1000 <= Date.now();
}

function isAdminToken(token: string | null) {
  const roles = parseTokenPayload(token)?.roles || [];
  return roles.some((role) => ["admin_platform", "sales_admin", "sales_viewer", "sales_affiliate"].includes(role));
}

export function getAccessToken() {
  if (typeof window === 'undefined') return null;
  const token = window.localStorage.getItem(TOKEN_KEY);
  if (token && isExpiredToken(token)) {
    return token;
  }
  return token;
}

export function getRefreshToken() {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setAccessToken(token: string, refreshToken?: string | null) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(TOKEN_KEY, token);
  if (refreshToken === null) {
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  } else if (typeof refreshToken === 'string') {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  }
}

export function clearAccessToken() {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function getAdminAccessToken() {
  if (typeof window === 'undefined') return null;
  const adminToken = window.localStorage.getItem(ADM_TOKEN_KEY);
  if (adminToken && !isExpiredToken(adminToken)) return adminToken;
  if (adminToken && isExpiredToken(adminToken)) {
    window.localStorage.removeItem(ADM_TOKEN_KEY);
  }

  const legacyToken = window.localStorage.getItem(TOKEN_KEY);
  if (legacyToken && !isExpiredToken(legacyToken) && isAdminToken(legacyToken)) {
    return legacyToken;
  }
  if (legacyToken && isExpiredToken(legacyToken)) {
    window.localStorage.removeItem(TOKEN_KEY);
  }
  return null;
}

export function getAdminRefreshToken() {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(ADM_REFRESH_TOKEN_KEY);
}

export function setAdminAccessToken(token: string, refreshToken?: string | null) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(ADM_TOKEN_KEY, token);
  if (refreshToken === null) {
    window.localStorage.removeItem(ADM_REFRESH_TOKEN_KEY);
  } else if (typeof refreshToken === 'string') {
    window.localStorage.setItem(ADM_REFRESH_TOKEN_KEY, refreshToken);
  }
}

export function clearAdminAccessToken() {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(ADM_TOKEN_KEY);
  window.localStorage.removeItem(ADM_REFRESH_TOKEN_KEY);
  const legacyToken = window.localStorage.getItem(TOKEN_KEY);
  if (legacyToken && isAdminToken(legacyToken)) {
    window.localStorage.removeItem(TOKEN_KEY);
  }
}

export function hasSessionToken() {
  if (typeof window === 'undefined') return false;
  return Boolean(getAccessToken() || getRefreshToken());
}
