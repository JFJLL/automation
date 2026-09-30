export class ApiError extends Error {
  code: string;
  statusCode: number;

  constructor(message: string, code: string = 'API_ERROR', statusCode: number = 500) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.statusCode = statusCode;
  }
}

function getCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp('(^|;\s*)(' + name + ')=([^;]*)'));
  return match ? decodeURIComponent(match[3]) : null;
}

export async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const apiBase = String((import.meta as any).env?.VITE_API_BASE || '').replace(new RegExp('/$'), '');
  const fullUrl = url.startsWith('http') ? url : (apiBase + (url.startsWith('/') ? '' : '/') + url);

  const headers = new Headers(options.headers || {});
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  // Double submit CSRF protection: send X-CSRF-Token on all state mutation requests
  const method = (options.method || 'GET').toUpperCase();
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method) && !headers.has('X-CSRF-Token')) {
    const csrfToken = getCookie('csrf_token');
    if (csrfToken) {
      headers.set('X-CSRF-Token', csrfToken);
    }
  }

  const response = await fetch(fullUrl, {
    ...options,
    headers,
    credentials: 'same-origin',
  });

  let data: any = null;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  } else {
    data = await response.text();
  }

  if (response.status === 401) {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('auth:unauthorized'));
    }
  }

  if (!response.ok) {
    const errorMsg = data?.error?.message || data?.detail || response.statusText || '请求异常';
    const errorCode = data?.error?.code || ('HTTP_' + response.status);
    throw new ApiError(errorMsg, errorCode, response.status);
  }

  return data as T;
}
