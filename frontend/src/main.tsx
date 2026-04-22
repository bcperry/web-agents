import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { fetchRuntimeConfig } from './config/runtimeConfig'
import './index.css'
import App from './App.tsx'

async function bootstrap() {
  const runtimeConfig = await fetchRuntimeConfig()
  document.title = runtimeConfig.appName

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

void bootstrap()
