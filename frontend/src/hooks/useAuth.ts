import { createContext, createElement, useContext, useState, useEffect, useCallback, useMemo, useRef, type ReactNode } from 'react';
import {
  PublicClientApplication,
  InteractionRequiredAuthError,
} from '@azure/msal-browser';
import type {
  Configuration,
  AccountInfo,
} from '@azure/msal-browser';
import { fetchRuntimeConfig, getRuntimeConfigSnapshot, type RuntimeConfig } from '../config/runtimeConfig';
import { AuthError, setTokenProvider } from '../api/helpers';

interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: { id: string; name: string; email: string } | null;
  classificationBanner: string;
  getToken: () => Promise<string | null>;
  login: () => Promise<void>;
  logout: () => void;
}

let msalInstance: PublicClientApplication | null = null;
let initialization: Promise<void> | null = null;
const AuthContext = createContext<AuthState | null>(null);

function getMsalInstance(clientId: string, authority: string, tenantId: string): PublicClientApplication {
  if (!msalInstance) {
    const msalConfig: Configuration = {
      auth: {
        clientId,
        authority: `${authority}/${tenantId}`,
        redirectUri: window.location.origin,
      },
      cache: {
        cacheLocation: 'localStorage',
      },
    };
    msalInstance = new PublicClientApplication(msalConfig);
  }
  return msalInstance;
}

function useAuthState(): AuthState {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [account, setAccount] = useState<AccountInfo | null>(null);
  const [authDisabled, setAuthDisabled] = useState(false);
  const configRef = useRef<RuntimeConfig | null>(null);

  const user = useMemo(() => {
    if (authDisabled) {
      return { id: 'dev-user', name: 'Developer', email: 'dev@localhost' };
    }
    if (!account) return null;
    return {
      id: account.localAccountId,
      name: account.name || account.username || 'Unknown',
      email: account.username || '',
    };
  }, [account, authDisabled]);

  useEffect(() => {
    const init = async () => {
      try {
        const cfg = await fetchRuntimeConfig();
        configRef.current = cfg;
        setAuthDisabled(cfg.authDisabled);

        if (cfg.authDisabled) {
          setIsAuthenticated(true);
          setIsLoading(false);
          return;
        }

        const msal = getMsalInstance(cfg.clientId, cfg.authority, cfg.tenantId);
        initialization ??= msal.initialize().then(async () => {
          const response = await msal.handleRedirectPromise();
          msal.setActiveAccount(response?.account ?? msal.getAllAccounts()[0] ?? null);
        });
        await initialization;
        const activeAccount = msal.getActiveAccount();
        setAccount(activeAccount);
        setIsAuthenticated(Boolean(activeAccount));
      } catch (err) {
        console.error('MSAL init error:', err);
      } finally {
        setIsLoading(false);
      }
    };

    init();
  }, []);

  const getToken = useCallback(async (): Promise<string | null> => {
    const cfg = configRef.current;
    if (!cfg || cfg.authDisabled) return null;

    const msal = getMsalInstance(cfg.clientId, cfg.authority, cfg.tenantId);
    const activeAccount = msal.getActiveAccount();
    if (!activeAccount) throw new AuthError('Please sign in to continue.');

    const scopes = [`${cfg.clientId}/.default`];

    try {
      const response = await msal.acquireTokenSilent({
        scopes,
        account: activeAccount,
      });
      return response.accessToken;
    } catch (err) {
      if (err instanceof InteractionRequiredAuthError) {
        setIsAuthenticated(false);
        throw new AuthError('Your session has expired. Please sign in again.');
      }
      throw err;
    }
  }, []);

  const login = useCallback(async () => {
    const cfg = configRef.current;
    if (!cfg || cfg.authDisabled) return;

    const scopes = [`${cfg.clientId}/.default`];
    const msal = getMsalInstance(cfg.clientId, cfg.authority, cfg.tenantId);
    try {
      await msal.loginRedirect({ scopes });
    } catch (err) {
      console.error('Login error:', err);
    }
  }, []);

  const logout = useCallback(() => {
    const cfg = configRef.current;
    localStorage.removeItem('auth_token');
    if (!cfg || cfg.authDisabled) return;

    const msal = getMsalInstance(cfg.clientId, cfg.authority, cfg.tenantId);
    msal.logoutRedirect();
  }, []);

  const classificationBanner =
    configRef.current?.classificationBanner || getRuntimeConfigSnapshot().classificationBanner;

  return { isAuthenticated, isLoading, user, classificationBanner, getToken, login, logout };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const state = useAuthState();
  useEffect(() => {
    localStorage.removeItem('auth_token');
    setTokenProvider(state.getToken);
  }, [state.getToken]);
  return createElement(AuthContext.Provider, { value: state }, children);
}

export function useAuth(): AuthState {
  const state = useContext(AuthContext);
  if (!state) throw new Error('useAuth requires AuthProvider');
  return state;
}
