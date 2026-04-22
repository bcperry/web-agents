import { useAuth } from './hooks/useAuth'
import { ThemeProvider } from './hooks/useTheme'
import { ToastProvider } from './hooks/useToast'
import { ChatPage } from './pages/ChatPage'
import { Disclaimer } from './components/Disclaimer'
import { getRuntimeConfigSnapshot } from './config/runtimeConfig'
import './styles/index.css'

function AppContent() {
  const { isAuthenticated, isLoading, login } = useAuth()
  const { appName } = getRuntimeConfigSnapshot()

  if (isLoading) {
    return (
      <div className="app-loading">
        <div className="loading-indicator">Loading...</div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <Disclaimer>
        <div className="app-login">
          <h1>{appName}</h1>
          <p>AUTHENTICATION REQUIRED</p>
          <button className="login-btn" onClick={login} type="button">
            AUTHENTICATE
          </button>
        </div>
      </Disclaimer>
    )
  }

  return (
    <Disclaimer>
      <ChatPage />
    </Disclaimer>
  )
}

function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AppContent />
      </ToastProvider>
    </ThemeProvider>
  )
}

export default App
