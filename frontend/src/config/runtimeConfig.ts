export const DEFAULT_APP_NAME = 'Web-Agents';
export const DEFAULT_APP_TAGLINE = 'AI Agent Framework';
export const DEFAULT_APP_LOGO = '/Microsoft.png';

const DEFAULT_AUTHORITY = 'https://login.microsoftonline.us';
const DEFAULT_CLASSIFICATION_BANNER = 'UNCLASSIFIED';

declare const __AUTH_DISABLED__: string;
declare const __AZURE_AD_TENANT_ID__: string;
declare const __AZURE_AD_CLIENT_ID__: string;
declare const __CLASSIFICATION_BANNER__: string;

export interface RuntimeConfig {
  authDisabled: boolean;
  tenantId: string;
  clientId: string;
  authority: string;
  classificationBanner: string;
  appName: string;
  appTagline: string;
  appLogo: string;
}

function normalizeConfig(payload: Partial<RuntimeConfig>): RuntimeConfig {
  return {
    authDisabled: Boolean(payload.authDisabled),
    tenantId: payload.tenantId?.trim() || '',
    clientId: payload.clientId?.trim() || '',
    authority: payload.authority?.trim() || DEFAULT_AUTHORITY,
    classificationBanner: payload.classificationBanner?.trim() || DEFAULT_CLASSIFICATION_BANNER,
    appName: payload.appName?.trim() || DEFAULT_APP_NAME,
    appTagline: payload.appTagline?.trim() || DEFAULT_APP_TAGLINE,
    appLogo: payload.appLogo?.trim() || DEFAULT_APP_LOGO,
  };
}

function buildFallbackConfig(): RuntimeConfig {
  return normalizeConfig({
    authDisabled: typeof __AUTH_DISABLED__ !== 'undefined' && __AUTH_DISABLED__ === 'true',
    tenantId: typeof __AZURE_AD_TENANT_ID__ !== 'undefined' ? __AZURE_AD_TENANT_ID__ : '',
    clientId: typeof __AZURE_AD_CLIENT_ID__ !== 'undefined' ? __AZURE_AD_CLIENT_ID__ : '',
    authority: import.meta.env.VITE_AZURE_AD_AUTHORITY || DEFAULT_AUTHORITY,
    classificationBanner:
      typeof __CLASSIFICATION_BANNER__ !== 'undefined'
        ? __CLASSIFICATION_BANNER__
        : DEFAULT_CLASSIFICATION_BANNER,
  });
}

let cachedConfig: RuntimeConfig | null = null;
let pendingConfig: Promise<RuntimeConfig> | null = null;

export async function fetchRuntimeConfig(): Promise<RuntimeConfig> {
  if (cachedConfig) {
    return cachedConfig;
  }

  if (!pendingConfig) {
    pendingConfig = (async () => {
      try {
        const resp = await fetch('/api/auth/config');
        if (resp.ok) {
          cachedConfig = normalizeConfig(await resp.json() as Partial<RuntimeConfig>);
          return cachedConfig;
        }
      } catch {
        // Fall through to local defaults when backend config is unavailable.
      }

      cachedConfig = buildFallbackConfig();
      return cachedConfig;
    })().finally(() => {
      pendingConfig = null;
    });
  }

  return pendingConfig;
}

export function getRuntimeConfigSnapshot(): RuntimeConfig {
  return cachedConfig ?? buildFallbackConfig();
}