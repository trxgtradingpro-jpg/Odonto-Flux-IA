import axios from 'axios';

import {
  clearAccessToken,
  clearAdminAccessToken,
  getAccessToken,
  getAdminAccessToken,
  getAdminRefreshToken,
  getRefreshToken,
  setAccessToken,
  setAdminAccessToken,
} from './auth';

const DIRECT_RENDER_API_BASE = 'https://odontoflux-api.onrender.com/api/v1';
const DIRECT_API_HOSTNAMES = new Set(['clinicfluxai.com.br', 'www.clinicfluxai.com.br']);

function resolveApiBase(): string {
  const configuredBase = process.env.NEXT_PUBLIC_API_URL;

  if (typeof window !== 'undefined' && DIRECT_API_HOSTNAMES.has(window.location.hostname.toLowerCase())) {
    return configuredBase || DIRECT_RENDER_API_BASE;
  }

  // When running on Render with separate web/api services, prefer direct API URL.
  // This avoids depending on Next rewrites that may be baked with docker-build defaults.
  if (typeof window !== 'undefined' && window.location.hostname.endsWith('.onrender.com')) {
    const apiHost = window.location.hostname.replace('-web.', '-api.');
    if (apiHost !== window.location.hostname) {
      return `https://${apiHost}/api/v1`;
    }
  }

  return configuredBase || '/api/v1';
}

const apiBase = resolveApiBase();

export const api = axios.create({
  baseURL: apiBase,
  timeout: 20_000,
});

const refreshApi = axios.create({
  baseURL: apiBase,
  timeout: 20_000,
});

let refreshPromise: Promise<string | null> | null = null;

async function refreshCurrentSession(isAdmRoute: boolean) {
  const currentRefreshToken = isAdmRoute ? getAdminRefreshToken() : getRefreshToken();
  if (!currentRefreshToken) return null;

  if (!refreshPromise) {
    refreshPromise = refreshApi
      .post('/auth/refresh', { refresh_token: currentRefreshToken })
      .then((response) => {
        const data = response.data as { access_token: string; refresh_token: string };
        if (isAdmRoute) {
          setAdminAccessToken(data.access_token, data.refresh_token);
        } else {
          setAccessToken(data.access_token, data.refresh_token);
        }
        return data.access_token;
      })
      .catch(() => {
        if (isAdmRoute) {
          clearAdminAccessToken();
        } else {
          clearAccessToken();
        }
        return null;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }

  return refreshPromise;
}

api.interceptors.request.use((config) => {
  const isAdmRoute = typeof window !== 'undefined' && window.location.pathname.startsWith('/adm');
  const token = isAdmRoute ? getAdminAccessToken() : getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      const isAdmRoute = typeof window !== 'undefined' && window.location.pathname.startsWith('/adm');
      const requestUrl = String(error.config?.url || '');
      const isAdmLoginRequest = requestUrl.includes('/admin/auth/login');
      const isRefreshRequest = requestUrl.includes('/auth/refresh');
      const code = error.response?.data?.error?.code;
      const tokenIsInvalid = ['AUTH_INVALID_TOKEN', 'AUTH_INVALID_TOKEN_TYPE', 'AUTH_INVALID_USER'].includes(code);

      if (!error.config?._retry && !isAdmLoginRequest && !isRefreshRequest) {
        error.config._retry = true;
        const newAccessToken = await refreshCurrentSession(isAdmRoute);
        if (newAccessToken) {
          error.config.headers = error.config.headers ?? {};
          error.config.headers.Authorization = `Bearer ${newAccessToken}`;
          return api.request(error.config);
        }
      }

      if (isAdmRoute && !isAdmLoginRequest) {
        clearAdminAccessToken();
        if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/adm')) {
          window.location.href = '/adm';
        }
      } else if (!isAdmRoute || tokenIsInvalid || isRefreshRequest) {
        clearAccessToken();
      }
      if (
        typeof window !== 'undefined' &&
        !window.location.pathname.includes('/login') &&
        !window.location.pathname.startsWith('/adm')
      ) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);
