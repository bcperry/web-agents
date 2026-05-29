import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  PublicClientApplication,
  InteractionRequiredAuthError,
} from '@azure/msal-browser';
import type {
  Configuration,
  AccountInfo,
} from '@azure/msal-browser';
import { fetchRuntimeConfig, getRuntimeConfigSnapshot, type RuntimeConfig } from '../config/runtimeConfig';

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

export function useAuth(): AuthState {
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

        const scopes = [`${cfg.clientId}/.default`];
        const msal = getMsalInstance(cfg.clientId, cfg.authority, cfg.tenantId);
        await msal.initialize();
        const response = await msal.handleRedirectPromise();
        if (response?.account) {
          msal.setActiveAccount(response.account);
          setAccount(response.account);
          setIsAuthenticated(true);
          if (response.accessToken) {
            localStorage.setItem('auth_token', response.accessToken);
          }
        } else {
          const accounts = msal.getAllAccounts();
          if (accounts.length > 0) {
            msal.setActiveAccount(accounts[0]);
            setAccount(accounts[0]);
            setIsAuthenticated(true);
            try {
              const tokenResponse = await msal.acquireTokenSilent({
                scopes,
                account: accounts[0],
              });
              if (tokenResponse.accessToken) {
                localStorage.setItem('auth_token', tokenResponse.accessToken);
              }
            } catch {
              // Token will be acquired on next API call via getToken()
            }
          }
        }
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
    if (!activeAccount) return null;

    const scopes = [`${cfg.clientId}/.default`];

    try {
      const response = await msal.acquireTokenSilent({
        scopes,
        account: activeAccount,
      });
      if (response.accessToken) {
        localStorage.setItem('auth_token', response.accessToken);
      }
      return response.accessToken;
    } catch (err) {
      if (err instanceof InteractionRequiredAuthError) {
        try {
          const response = await msal.acquireTokenPopup({ scopes });
          if (response.accessToken) {
            localStorage.setItem('auth_token', response.accessToken);
          }
          return response.accessToken;
        } catch (popupErr) {
          console.error('Token acquisition failed:', popupErr);
          return null;
        }
      }
      console.error('Silent token error:', err);
      return null;
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
