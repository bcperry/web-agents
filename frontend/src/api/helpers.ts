import { emitToast } from '../hooks/useToast';

export const API_BASE = '/api';

/** Thrown when the backend returns 401 Unauthorized. */
export class AuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AuthError';
  }
}

export class RequestError extends Error {}

let tokenProvider: () => Promise<string | null> = async () => null;

export function setTokenProvider(provider: () => Promise<string | null>): void {
  tokenProvider = provider;
}

async function extractErrorDetail(resp: Response, fallback: string): Promise<string> {
  try {
    const body = await resp.json();
    if (body.detail && typeof body.detail === 'string') return body.detail;
    const errors = Array.isArray(body.detail) ? body.detail : body.detail?.errors;
    if (Array.isArray(errors)) {
      return errors.map((error: { field?: string; reason?: string; msg?: string; message?: string }) =>
        [error.field, error.reason ?? error.msg ?? error.message].filter(Boolean).join(': ')).join('; ') || fallback;
    }
  } catch { /* not JSON or no detail field */ }
  return fallback;
}

export async function fetchAuthenticated(url: string, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = await tokenProvider();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  return fetch(url, { ...init, headers });
}

export async function request(url: string, init: RequestInit, context: string, accepted: number[] = []): Promise<Response> {
  let resp: Response;
  try {
    resp = await fetchAuthenticated(url, init);
  } catch (error) {
    if (init.signal?.aborted || error instanceof AuthError) throw error;
    const message = `${context}: the server could not be reached. Please try again.`;
    emitToast({ message, type: 'error' });
    throw new RequestError(message, { cause: error });
  }
  if (resp.status === 401) throw new AuthError(`Unauthorized: ${context}`);
  if (!resp.ok && !accepted.includes(resp.status)) {
    const detail = await extractErrorDetail(resp, `${context}: ${resp.status}`);
    const rateLimited = resp.status === 429 || /rate limit|too many requests/i.test(detail);
    emitToast({ message: detail, type: rateLimited ? 'warning' : 'error' });
    throw new RequestError(detail);
  }
  return resp;
}

export async function requestJson<T>(url: string, init: RequestInit, context: string): Promise<T> {
  const resp = await request(url, init, context);
  return resp.json() as Promise<T>;
}