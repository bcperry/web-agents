import { useState, useEffect, useCallback, lazy, Suspense } from 'react'
import { AuthProvider, useAuth } from './hooks/useAuth'
import { useBuiltInAgentCustomizations } from './hooks/useBuiltInAgentCustomizations'
import { useCustomAgents } from './hooks/useCustomAgents'
import { useConversationStore } from './hooks/useConversationStore'
import { ThemeProvider } from './hooks/useTheme'
import { ToastProvider } from './hooks/useToast'
import { ChatPage } from './pages/ChatPage'
import type { AdminOpenOptions } from './pages/AdminPage'
import { Disclaimer } from './components/Disclaimer'
import { getRuntimeConfigSnapshot } from './config/runtimeConfig'
import './styles/index.css'

const AdminPage = lazy(() => import('./pages/AdminPage').then(module => ({ default: module.AdminPage })))
const AutonomousPage = lazy(() => import('./pages/AutonomousPage').then(module => ({ default: module.AutonomousPage })))

function AppContent() {
  const { user } = useAuth()
  const [currentView, setCurrentView] = useState<'chat' | 'admin' | 'autonomous'>('chat')
  const [adminIntent, setAdminIntent] = useState<AdminOpenOptions | undefined>(undefined)
  const {
    agents: customAgents,
    save: saveCustomAgent,
    remove: removeCustomAgent,
    reload: reloadCustomAgents,
  } = useCustomAgents()
  const {
    overrides: builtInOverrides,
    save: saveBuiltInOverride,
    remove: resetBuiltInOverride,
  } = useBuiltInAgentCustomizations()
  const { deleteConversationsByCustomAgent } = useConversationStore()

  // Initialise history state so the back button can return here from admin.
  useEffect(() => {
    window.history.replaceState({ view: 'chat' }, '')
  }, [])

  // Sync currentView with browser back/forward navigation.
  useEffect(() => {
    const handlePopState = (e: PopStateEvent) => {
      const view = (e.state as { view?: string } | null)?.view
      setCurrentView(view === 'admin' ? 'admin' : view === 'autonomous' ? 'autonomous' : 'chat')
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  const handleOpenAdmin = useCallback((opts?: AdminOpenOptions) => {
    setAdminIntent(opts)
    window.history.pushState({ view: 'admin' }, '')
    setCurrentView('admin')
  }, [])

  const handleAdminBack = useCallback(() => {
    // Let the browser pop the history entry; the popstate listener updates the view.
    window.history.back()
  }, [])

  const handleOpenAutonomous = useCallback(() => {
    window.history.pushState({ view: 'autonomous' }, '')
    setCurrentView('autonomous')
  }, [])

  const handleAutonomousBack = useCallback(() => {
    window.history.back()
  }, [])

  const handleDeleteAgent = async (id: string) => {
    await removeCustomAgent(id)
    await deleteConversationsByCustomAgent(id)
  }

  return (
    <Disclaimer>
      <Suspense fallback={<div className="app-loading">Loading...</div>}>
      {currentView === 'admin' ? (
        <AdminPage
          onBack={handleAdminBack}
          userEmail={user?.email}
          initialTab={adminIntent?.tab}
          automationCreate={adminIntent?.automationCreate}
          automationEditId={adminIntent?.automationEditId}
          agents={customAgents}
          builtInOverrides={builtInOverrides}
          onSaveAgent={saveCustomAgent}
          onDeleteAgent={handleDeleteAgent}
          onSaveBuiltInOverride={saveBuiltInOverride}
          onResetBuiltInOverride={resetBuiltInOverride}
        />
      ) : currentView === 'autonomous' ? (
        <AutonomousPage onBack={handleAutonomousBack} onOpenAdmin={handleOpenAdmin} />
      ) : (
        <ChatPage
          onOpenAdmin={handleOpenAdmin}
          onOpenAutonomous={handleOpenAutonomous}
          onCustomAgentsChanged={reloadCustomAgents}
          customAgents={customAgents}
          builtInOverrides={builtInOverrides}
        />
      )}
      </Suspense>
    </Disclaimer>
  )
}

function AuthenticatedApp() {
  const { isAuthenticated, isLoading, login } = useAuth()
  if (isLoading) return <div className="app-loading">Loading...</div>
  if (!isAuthenticated) return (
    <Disclaimer>
      <div className="app-login">
        <h1>{getRuntimeConfigSnapshot().appName}</h1>
        <p>AUTHENTICATION REQUIRED</p>
        <button className="login-btn" onClick={login} type="button">AUTHENTICATE</button>
      </div>
    </Disclaimer>
  )
  return <AppContent />
}

function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AuthProvider><AuthenticatedApp /></AuthProvider>
      </ToastProvider>
    </ThemeProvider>
  )
}

export default App
