import { useState } from 'react'
import { useAuth } from './hooks/useAuth'
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
  const { isAuthenticated, isLoading, login } = useAuth()
  const { appName } = getRuntimeConfigSnapshot()
  const [currentView, setCurrentView] = useState<'chat' | 'admin'>('chat')
  const { agents: customAgents, save: saveCustomAgent, remove: removeCustomAgent } = useCustomAgents()
  const { loadIndex, deleteConversationsByCustomAgent } = useConversationStore()

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
          onBack={() => setCurrentView('chat')}
          agents={customAgents}
          onSaveAgent={saveCustomAgent}
          onDeleteAgent={handleDeleteAgent}
        />
      ) : (
        <ChatPage
          onOpenAdmin={() => setCurrentView('admin')}
          customAgents={customAgents}
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
