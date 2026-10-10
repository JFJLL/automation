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

export async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(url, {
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

  if (!response.ok) {
    let errorMsg = '请求异常';
    if (data && typeof data === 'object') {
      errorMsg = data.error?.message || data.detail || data.message || response.statusText || errorMsg;
    } else if (typeof data === 'string' && data.trim()) {
      try {
        const parsed = JSON.parse(data);
        errorMsg = parsed.error?.message || parsed.detail || parsed.message || data;
      } catch {
        if (data.includes('<html') || data.includes('<!DOCTYPE') || data.includes('<body')) {
          errorMsg = `网关服务响应异常 (HTTP ${response.status} ${response.statusText || 'Error'})`.trim();
        } else {
          errorMsg = data.slice(0, 150);
        }
      }
    } else if (response.statusText) {
      errorMsg = response.statusText;
    }
    const errorCode = (data && typeof data === 'object' && data.error?.code) || `HTTP_${response.status}`;
    throw new ApiError(errorMsg, errorCode, response.status);
  }

  return data as T;
}

