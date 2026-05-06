const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

async function readResponse(response) {
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof payload === 'string' ? payload : payload.detail || 'Request failed';
    throw new Error(detail);
  }
  return payload;
}

export async function apiFetch(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });
  return readResponse(response);
}

export function getWsBaseUrl() {
  return API_BASE_URL.replace(/^http/, 'ws');
}

export function getApiBaseUrl() {
  return API_BASE_URL;
}
