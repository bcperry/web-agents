import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';

export type ThemeMode = 'light' | 'dark';

const VALID_MODES: ThemeMode[] = ['light', 'dark'];
const STORAGE_KEY = 'webagents_theme';
const DEFAULT_MODE: ThemeMode = 'light';

interface ThemeContextValue {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
  colorScheme: 'light' | 'dark';
  activeAgentId: string | null;
  setActiveAgentId: (id: string | null) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStoredMode(): ThemeMode {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored && VALID_MODES.includes(stored as ThemeMode)) {
    return stored as ThemeMode;
  }
  return DEFAULT_MODE;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(readStoredMode);
  const [activeAgentId, setActiveAgentId] = useState<string | null>(null);

  const colorScheme = mode;

  const setMode = (newMode: ThemeMode) => {
    setModeState(newMode);
    localStorage.setItem(STORAGE_KEY, newMode);
  };

  // Apply data-theme attribute on <html> whenever colorScheme changes
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', colorScheme);
  }, [colorScheme]);

  return (
    <ThemeContext.Provider value={{ mode, setMode, colorScheme, activeAgentId, setActiveAgentId }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return ctx;
}
