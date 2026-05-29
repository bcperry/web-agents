import { useState, useEffect, useCallback } from 'react'
import { useAuth } from './hooks/useAuth'
import { useBuiltInAgentCustomizations } from './hooks/useBuiltInAgentCustomizations'
import { useCustomAgents } from './hooks/useCustomAgents'
import { useConversationStore } from './hooks/useConversationStore'
import { ThemeProvider } from './hooks/useTheme'
import { ToastProvider } from './hooks/useToast'
import { ChatPage } from './pages/ChatPage'
import { AdminPage } from './pages/AdminPage'
import { Disclaimer } from './components/Disclaimer'
import { getRuntimeConfigSnapshot } from './config/runtimeConfig'
import './styles/index.css'

function AppContent() {
  const { isAuthenticated, isLoading, login, user } = useAuth()
  const { appName } = getRuntimeConfigSnapshot()
  const [currentView, setCurrentView] = useState<'chat' | 'admin'>('chat')
  const { agents: customAgents, save: saveCustomAgent, remove: removeCustomAgent } = useCustomAgents()
  const {
    overrides: builtInOverrides,
    save: saveBuiltInOverride,
    remove: resetBuiltInOverride,
  } = useBuiltInAgentCustomizations()
  const { loadIndex, deleteConversationsByCustomAgent } = useConversationStore()

  // Initialise history state so the back button can return here from admin.
  useEffect(() => {
    window.history.replaceState({ view: 'chat' }, '')
  }, [])

  // Sync currentView with browser back/forward navigation.
  useEffect(() => {
    const handlePopState = (e: PopStateEvent) => {
      const view = (e.state as { view?: string } | null)?.view
      setCurrentView(view === 'admin' ? 'admin' : 'chat')
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  const handleOpenAdmin = useCallback(() => {
    window.history.pushState({ view: 'admin' }, '')
    setCurrentView('admin')
  }, [])

  const handleAdminBack = useCallback(() => {
    // Let the browser pop the history entry; the popstate listener updates the view.
    window.history.back()
  }, [])

  const handleDeleteAgent = (id: string) => {
    removeCustomAgent(id)
    deleteConversationsByCustomAgent(id)
    loadIndex()
  }

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
      {currentView === 'admin' ? (
        <AdminPage
          onBack={handleAdminBack}
          userEmail={user?.email}
          agents={customAgents}
          builtInOverrides={builtInOverrides}
          onSaveAgent={saveCustomAgent}
          onDeleteAgent={handleDeleteAgent}
          onSaveBuiltInOverride={saveBuiltInOverride}
          onResetBuiltInOverride={resetBuiltInOverride}
        />
      ) : (
        <ChatPage
          onOpenAdmin={handleOpenAdmin}
          customAgents={customAgents}
          builtInOverrides={builtInOverrides}
        />
      )}
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
