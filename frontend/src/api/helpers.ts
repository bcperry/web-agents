import { emitToast } from '../hooks/useToast';

export const API_BASE = '/api';

/** Thrown when the backend returns 401 Unauthorized. */
export class AuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AuthError';
  }
}

export function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('auth_token');
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

export function assertNotUnauthorized(resp: Response, context: string): void {
  if (resp.status === 401) {
    throw new AuthError(`Unauthorized: ${context}`);
  }
}

async function extractErrorDetail(resp: Response, fallback: string): Promise<string> {
  try {
    const body = await resp.json();
    if (body.detail && typeof body.detail === 'string') return body.detail;
  } catch { /* not JSON or no detail field */ }
  return fallback;
}

export function classifyError(status: number, detail: string): {
  userMessage: string;
  type: 'error' | 'warning';
  retryable: boolean;
} {
  const lowerDetail = detail.toLowerCase();

  if (status === 429 || lowerDetail.includes('rate limit') || lowerDetail.includes('too many requests')) {
    return { userMessage: detail || 'Rate limit exceeded. Please wait and try again.', type: 'warning', retryable: true };
  }
  if (status === 400) {
    return { userMessage: detail || 'Invalid request.', type: 'error', retryable: false };
  }
  if (status >= 500) {
    return { userMessage: detail || 'A server error occurred. Please try again later.', type: 'error', retryable: false };
  }
  return { userMessage: detail || `Request failed (${status})`, type: 'error', retryable: false };
}

export async function handleHttpError(resp: Response, context: string): Promise<never> {
  const detail = await extractErrorDetail(resp, `${context}: ${resp.status}`);
  const classified = classifyError(resp.status, detail);
  emitToast({ message: classified.userMessage, type: classified.type });
  throw new Error(detail);
}

export function jsonHeaders(): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    ...getAuthHeaders(),
  };
}

export async function requestJson<T>(url: string, init: RequestInit, context: string): Promise<T> {
  const resp = await fetch(url, init);
  assertNotUnauthorized(resp, context);
  if (!resp.ok) await handleHttpError(resp, context);
  return resp.json() as Promise<T>;
}