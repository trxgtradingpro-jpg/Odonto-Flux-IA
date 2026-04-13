import axios from 'axios';

import { clearAccessToken, getAccessToken } from './auth';

function resolveApiBase(): string {
  const configuredBase = process.env.NEXT_PUBLIC_API_URL;

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

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearAccessToken();
      if (typeof window !== 'undefined' && !window.location.pathname.includes('/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);
