import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import type { ReactNode } from 'react';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastEvent {
  message: string;
  type: 'error' | 'warning';
  duration?: number;
  action?: ToastAction;
}

export interface Toast {
  id: string;
  message: string;
  type: 'error' | 'warning';
  duration: number;
  createdAt: number;
  action?: ToastAction;
}

/* ------------------------------------------------------------------ */
/*  Global event emitter (imperative bridge for non-React code)        */
/* ------------------------------------------------------------------ */

const toastEmitter = new EventTarget();
const TOAST_EVENT = 'toast';

const DEFAULT_DURATION = 8000;
const MAX_TOASTS = 5;
const MIN_DURATION = 2000;
const MAX_DURATION = 30000;

function clampDuration(d: number): number {
  return Math.max(MIN_DURATION, Math.min(MAX_DURATION, d));
}

/** Fire a toast from anywhere — no React dependency required. */
export function emitToast(event: ToastEvent): void {
  toastEmitter.dispatchEvent(new CustomEvent(TOAST_EVENT, { detail: event }));
}

/* ------------------------------------------------------------------ */
/*  React context                                                      */
/* ------------------------------------------------------------------ */

interface ToastContextValue {
  toasts: Toast[];
  showToast: (event: ToastEvent) => void;
  dismissToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const pausedRef = useRef<Set<string>>(new Set());

  const dismissToast = useCallback((id: string) => {
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
    pausedRef.current.delete(id);
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const startTimer = useCallback((id: string, duration: number) => {
    const timer = setTimeout(() => {
      timersRef.current.delete(id);
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, duration);
    timersRef.current.set(id, timer);
  }, []);

  const showToast = useCallback((event: ToastEvent) => {
    if (!event.message) return;
    const id = crypto.randomUUID();
    const duration = clampDuration(event.duration ?? DEFAULT_DURATION);
    const toast: Toast = {
      id,
      message: event.message,
      type: event.type,
      duration,
      createdAt: Date.now(),
      action: event.action,
    };
    setToasts((prev) => {
      const next = [...prev, toast];
      // Enforce max cap — remove oldest
      while (next.length > MAX_TOASTS) {
        const removed = next.shift()!;
        const timer = timersRef.current.get(removed.id);
        if (timer) {
          clearTimeout(timer);
          timersRef.current.delete(removed.id);
        }
        pausedRef.current.delete(removed.id);
      }
      return next;
    });
    startTimer(id, duration);
  }, [startTimer]);

  // Pause / resume auto-dismiss on hover
  const pauseToast = useCallback((id: string) => {
    pausedRef.current.add(id);
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const resumeToast = useCallback((id: string) => {
    if (!pausedRef.current.has(id)) return;
    pausedRef.current.delete(id);
    // Find remaining toast to get its duration
    setToasts((prev) => {
      const toast = prev.find((t) => t.id === id);
      if (toast) {
        // Resume with remaining half of original duration (at least 2s)
        startTimer(id, Math.max(MIN_DURATION, toast.duration / 2));
      }
      return prev;
    });
  }, [startTimer]);

  // Subscribe to imperative emitToast() events
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<ToastEvent>).detail;
      showToast(detail);
    };
    toastEmitter.addEventListener(TOAST_EVENT, handler);
    return () => toastEmitter.removeEventListener(TOAST_EVENT, handler);
  }, [showToast]);

  // Cleanup timers on unmount
  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      for (const timer of timers.values()) clearTimeout(timer);
      timers.clear();
    };
  }, []);

  return (
    <ToastContext.Provider value={{ toasts, showToast, dismissToast }}>
      {children}
      {/* ToastContainer is rendered here but defined in Toast.tsx */}
      <ToastContainerPortal
        toasts={toasts}
        onDismiss={dismissToast}
        onPause={pauseToast}
        onResume={resumeToast}
      />
    </ToastContext.Provider>
  );
}

export function useToast(): { showToast: (event: ToastEvent) => void; dismissToast: (id: string) => void } {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return { showToast: ctx.showToast, dismissToast: ctx.dismissToast };
}

/* ------------------------------------------------------------------ */
/*  Inline ToastContainer (keeps everything in one provider file)      */
/* ------------------------------------------------------------------ */

function ToastContainerPortal({
  toasts,
  onDismiss,
  onPause,
  onResume,
}: {
  toasts: Toast[];
  onDismiss: (id: string) => void;
  onPause: (id: string) => void;
  onResume: (id: string) => void;
}) {
  if (toasts.length === 0) return null;
  return (
    <div className="toast-container" role="status" aria-live="polite">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`toast toast--${toast.type}`}
          onMouseEnter={() => onPause(toast.id)}
          onMouseLeave={() => onResume(toast.id)}
        >
          <span className="toast__message">{toast.message}</span>
          <div className="toast__actions">
            {toast.action && (
              <button
                className="toast__action-btn"
                onClick={() => {
                  toast.action!.onClick();
                  onDismiss(toast.id);
                }}
                type="button"
              >
                {toast.action.label}
              </button>
            )}
            <button
              className="toast__close"
              onClick={() => onDismiss(toast.id)}
              type="button"
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
