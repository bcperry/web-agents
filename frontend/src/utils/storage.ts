export function readJson<T>(key: string, fallback: T, validate?: (value: unknown) => value is T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as unknown;
    if (validate && !validate(parsed)) {
      localStorage.removeItem(key);
      return fallback;
    }
    return parsed as T;
  } catch {
    try { localStorage.removeItem(key); } catch { /* ignore */ }
    return fallback;
  }
}

export function writeJson<T>(key: string, value: T): void {
  localStorage.setItem(key, JSON.stringify(value));
}

export function tryWriteJson<T>(key: string, value: T, onError?: (error: unknown) => void): void {
  try {
    writeJson(key, value);
  } catch (error) {
    onError?.(error);
  }
}

export function removeStorageItem(key: string): void {
  try { localStorage.removeItem(key); } catch { /* ignore */ }
}