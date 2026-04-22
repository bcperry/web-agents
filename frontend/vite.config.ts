import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load all env vars from the repo root (shared .env with backend)
  const env = loadEnv(mode, '..', '')

  return {
    plugins: [react()],
    // Read .env from repo root so frontend and backend share one file
    envDir: '..',
    define: {
      // Map backend env var names to frontend globals
      '__AUTH_DISABLED__': JSON.stringify(env.AUTH_DISABLED || ''),
      '__AZURE_AD_TENANT_ID__': JSON.stringify(env.OAUTH_AZURE_GOV_AD_TENANT_ID || ''),
      '__AZURE_AD_CLIENT_ID__': JSON.stringify(env.OAUTH_AZURE_GOV_AD_CLIENT_ID || ''),
      '__CLASSIFICATION_BANNER__': JSON.stringify(env.CLASSIFICATION_BANNER || 'UNCLASSIFIED'),
      '__MAX_SESSIONS__': JSON.stringify(env.MAX_SESSIONS || '5'),
    },
    server: {
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
    },
  }
})
