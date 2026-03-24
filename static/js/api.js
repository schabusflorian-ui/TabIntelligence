// TabIntelligence API Client Module

const API_BASE = '/api/v1';

/** Get the stored API key */
export function getApiKey() {
  return localStorage.getItem('df_api_key') || '';
}

/** Save API key to localStorage */
export function setApiKey(key) {
  if (key) {
    localStorage.setItem('df_api_key', key.trim());
  }
}

/** Check if API key is configured */
export function hasApiKey() {
  return !!getApiKey();
}

/**
 * Authenticated fetch wrapper.
 * Automatically adds Bearer token and handles common error codes.
 * Returns the Response object (caller should .json() or .blob() as needed).
 */
export async function apiFetch(path, opts = {}) {
  const key = getApiKey();
  if (!key) throw new ApiError('API key is required. Configure it in the sidebar.', 0);

  const timeout = opts.timeout || 30000;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  // Allow callers to pass their own signal (e.g. for request cancellation)
  if (opts.signal) {
    opts.signal.addEventListener('abort', () => controller.abort());
  }

  const headers = {
    Authorization: 'Bearer ' + key,
    ...(opts.headers || {}),
  };

  const url = path.startsWith('http') || path.startsWith('/') ? path : API_BASE + '/' + path;

  let res;
  try {
    res = await fetch(url, { ...opts, headers, signal: controller.signal });
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === 'AbortError') {
      throw new ApiError('Request timed out', 0);
    }
    throw err;
  }
  clearTimeout(timeoutId);

  if (res.status === 401) throw new ApiError('Invalid API key', 401);
  if (res.status === 403) throw new ApiError('Forbidden — insufficient permissions', 403);
  if (res.status === 404) throw new ApiError('Not found', 404);
  if (res.status === 413) throw new ApiError('File too large', 413);
  if (res.status === 409) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.detail || 'Conflict', 409);
  }
  if (res.status === 422) {
    const body = await res.json().catch(() => ({}));
    const detail = body.detail;
    const msg = typeof detail === 'string' ? detail
      : Array.isArray(detail) ? detail.map(d => d.msg || JSON.stringify(d)).join('; ')
      : 'Validation error';
    throw new ApiError(msg, 422);
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.detail || `Request failed (${res.status})`, res.status);
  }

  return res;
}

/** Convenience: GET + parse JSON */
export async function apiGet(path, opts = {}) {
  const res = await apiFetch(path, opts);
  return res.json();
}

/** Convenience: POST JSON + parse JSON */
export async function apiPost(path, data) {
  const res = await apiFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

/** Convenience: PATCH JSON + parse JSON */
export async function apiPatch(path, data) {
  const res = await apiFetch(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

/** Convenience: DELETE */
export async function apiDelete(path) {
  return apiFetch(path, { method: 'DELETE' });
}

/** Custom error class with HTTP status */
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}
