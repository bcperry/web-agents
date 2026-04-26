import { useState, useEffect, useRef, useCallback } from 'react';
import type { AgentProfile, ConversationIndexEntry } from '../types/api';
import { fetchProfiles, AuthError } from '../api/client';
import { emitToast } from '../hooks/useToast';
import { useChat } from '../hooks/useChat';
import { useAuth } from '../hooks/useAuth';
import { useTheme } from '../hooks/useTheme';
import { useConversationStore } from '../hooks/useConversationStore';
import { ChatMessage } from '../components/ChatMessage';
import { ChatInput } from '../components/ChatInput';
import { ProfileSelector } from '../components/ProfileSelector';
import { StarterQuestions } from '../components/StarterQuestions';
import { TokenUsage } from '../components/TokenUsage';
import { AgentCapabilitiesBar } from '../components/AgentCapabilitiesBar';
import { Sidebar } from '../components/Sidebar';
import { getRuntimeConfigSnapshot } from '../config/runtimeConfig';
import type { CustomAgentDefinition } from '../types/api';

interface ChatPageProps {
  onOpenAdmin: () => void;
  customAgents: CustomAgentDefinition[];
}

export function ChatPage({ onOpenAdmin, customAgents }: ChatPageProps) {
  const [profiles, setProfiles] = useState<AgentProfile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<AgentProfile | null>(null);
  const [loadingProfiles, setLoadingProfiles] = useState(true);
  const [authError, setAuthError] = useState(false);
  const [creatingSession, setCreatingSession] = useState(false);
  const [spinnerTextIndex, setSpinnerTextIndex] = useState(0);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(window.innerWidth <= 768);
  const [conversationIndex, setConversationIndex] = useState<ConversationIndexEntry[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isEndingSessionRef = useRef(false);

  const SPINNER_MESSAGES = [
    'INITIALIZING AGENT RUNTIME...',
    'ESTABLISHING SECURE CONNECTION...',
    'LOADING MISSION PARAMETERS...',
    'FINDING THE T-1000...',
  ];

  const {
    messages,
    isStreaming,
    session,
    sessionUsage,
    mcpResults,
    toolsLoaded,
    skillsLoaded,
    searchContext,
    error,
    saveCounter,
    startSession,
    endSession,
    send,
    saveCurrentConversation,
  } = useChat();

  const { loadIndex, saveConversation, loadConversation, deleteConversation } = useConversationStore();
  const { user, logout, classificationBanner } = useAuth();
  const { setActiveAgentId } = useTheme();
  const { appName, appTagline, appLogo } = getRuntimeConfigSnapshot();

  // Merge server profiles with custom agents
  const allProfiles: AgentProfile[] = [
    ...profiles,
    ...customAgents.map((a) => ({
      id: a.id,
      name: a.name,
      description: a.description,
      icon: a.icon,
      starters: a.starters,
      isCustom: true as const,
    })),
  ];

  // Load profiles and conversation index on mount
  useEffect(() => {
    fetchProfiles()
      .then(({ profiles: p, unavailable }) => {
        setProfiles(p);
        for (const agent of unavailable) {
          emitToast({
            message: `${agent.name} unavailable: ${agent.reason}`,
            type: 'warning',
          });
        }
      })
      .catch((err) => {
        if (err instanceof AuthError) {
          setAuthError(true);
        }
        console.error('Failed to load profiles:', err);
      })
      .finally(() => setLoadingProfiles(false));
    setConversationIndex(loadIndex());
  }, [loadIndex]);

  // Refresh conversation index whenever a save completes
  useEffect(() => {
    if (saveCounter > 0) {
      setConversationIndex(loadIndex());
    }
  }, [saveCounter, loadIndex]);

  // Sync active agent ID with theme context for per-agent backgrounds
  useEffect(() => {
    setActiveAgentId(selectedProfile?.id ?? null);
  }, [selectedProfile, setActiveAgentId]);

  // Rotate spinner text while creating session
  useEffect(() => {
    if (!creatingSession) return;
    const interval = setInterval(() => {
      setSpinnerTextIndex((i) => (i + 1) % SPINNER_MESSAGES.length);
    }, 1800);
    return () => clearInterval(interval);
  }, [creatingSession]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleProfileSelect = useCallback(async (profileId: string) => {
    const profile = allProfiles.find((p) => p.id === profileId);
    if (profile) {
      setSelectedProfile(profile);
      setCreatingSession(true);
      setSpinnerTextIndex(0);
      try {
        if (profile.isCustom) {
          const customDef = customAgents.find((a) => a.id === profileId);
          if (customDef) {
            await startSession('custom', undefined, {
              customAgentId: customDef.id,
              custom_name: customDef.name,
              custom_prompt: customDef.systemPrompt,
              custom_tools: customDef.tools,
              custom_search_context: customDef.useSearchContext,
              mcp_servers: customDef.mcpServers,
              custom_temperature: customDef.temperature,
              custom_skills: customDef.skills,
            });
          }
        } else {
          await startSession(profileId);
        }
        // Push a history entry so the back button returns to profile selection.
        window.history.pushState({ view: 'chat-active' }, '');
      } finally {
        setCreatingSession(false);
      }
    }
  }, [allProfiles, customAgents, startSession]);

  const handleSend = (content: string, images?: File[]) => {
    send(content, images);
  };

  const handleNewChat = useCallback(async () => {
    if (isEndingSessionRef.current) return;
    isEndingSessionRef.current = true;
    try {
      // Save current conversation before switching
      await saveCurrentConversation();
      await endSession();
      setSelectedProfile(null);
      setConversationIndex(loadIndex());
      // Replace the chat-active history entry with a chat entry so the back
      // button doesn't try to re-enter a session that no longer exists.
      if ((window.history.state as { view?: string } | null)?.view === 'chat-active') {
        window.history.replaceState({ view: 'chat' }, '');
      }
    } finally {
      isEndingSessionRef.current = false;
    }
  }, [saveCurrentConversation, endSession, loadIndex]);

  // Handle browser back button: return to profile selection when leaving an active session.
  useEffect(() => {
    const handlePopState = (e: PopStateEvent) => {
      const view = (e.state as { view?: string } | null)?.view;
      if (view === 'chat' && session && !isEndingSessionRef.current) {
        void handleNewChat();
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [session, handleNewChat]);

  const handleSelectConversation = useCallback(async (id: string) => {
    // Save the current conversation if one is active
    if (session) {
      await saveCurrentConversation();
      // End the current session so the UI transitions to the spinner state
      await endSession();
    }

    const stored = loadConversation(id);
    if (!stored) return;

    // Touch lastActivityAt so resumed conversation moves to the top
    // and is protected from eviction as the "oldest"
    stored.lastActivityAt = new Date().toISOString();
    saveConversation(stored);
    setConversationIndex(loadIndex());

    const profile = allProfiles.find((p) => p.id === stored.profileId);
    setSelectedProfile(profile || null);
    setCreatingSession(true);
    setSpinnerTextIndex(0);

    // On mobile, close sidebar after selection
    if (window.innerWidth <= 768) {
      setSidebarCollapsed(true);
    }

    try {
      if (stored.customAgentId) {
        const customDef = customAgents.find((a) => a.id === stored.customAgentId);
        if (customDef) {
          await startSession('custom', stored, {
            customAgentId: customDef.id,
            custom_name: customDef.name,
            custom_prompt: customDef.systemPrompt,
            custom_tools: customDef.tools,
            custom_search_context: customDef.useSearchContext,
            mcp_servers: customDef.mcpServers,
            custom_temperature: customDef.temperature,
            custom_skills: customDef.skills,
          });
        } else {
          await startSession(stored.profileId, stored);
        }
      } else {
        await startSession(stored.profileId, stored);
      }
      // Push a history entry so the back button returns to profile selection,
      // but only if we're not already in an active session (switching conversations
      // should not add an extra back step).
      if ((window.history.state as { view?: string } | null)?.view !== 'chat-active') {
        window.history.pushState({ view: 'chat-active' }, '');
      }
    } finally {
      setCreatingSession(false);
    }
  }, [session, allProfiles, customAgents, startSession, endSession, saveCurrentConversation, loadConversation, saveConversation, loadIndex]);

  const handleDeleteConversation = useCallback((id: string) => {
    deleteConversation(id);
    setConversationIndex(loadIndex());
  }, [deleteConversation, loadIndex]);

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((prev) => !prev);
  }, []);

  // Main content
  const renderMainContent = () => {
    if (!session) {
      // Profile selection screen
      return (
        <div className="chat-page">
          <header className="chat-header">
            <div className="chat-header-brand">
              <button className="header-sidebar-toggle" onClick={toggleSidebar} type="button">☰</button>
              <img className="chat-header-logo" src={appLogo} alt={appName} />
              <div className="chat-header-titles">
                <h1 className="chat-title">{appName}</h1>
                <div className="chat-subtitle">{appTagline}</div>
              </div>
            </div>
          </header>
          <div className="chat-page-content">
            {loadingProfiles ? (
              <div className="loading-indicator">Loading profiles...</div>
            ) : authError ? (
              <div className="auth-error-panel">
                <h2>Unauthorized</h2>
                <p>Your session has expired or your credentials are invalid.</p>
                <button className="login-btn" onClick={logout} type="button">
                  Log In
                </button>
              </div>
            ) : creatingSession ? (
              <div className="session-spinner">
                <div className="spinner-ring" />
                <div className="spinner-text">{SPINNER_MESSAGES[spinnerTextIndex]}</div>
              </div>
            ) : (
              <ProfileSelector profiles={allProfiles} onSelect={handleProfileSelect} />
            )}
          </div>
          <footer className="classification-footer">
            {classificationBanner}
          </footer>
        </div>
      );
    }

    // Chat screen
    return (
      <div className="chat-page">
        <header className="chat-header">
          <div className="chat-header-brand">
            <button className="header-sidebar-toggle" onClick={toggleSidebar} type="button">☰</button>
            <img className="chat-header-logo" src={appLogo} alt={appName} />
            <div className="chat-header-titles">
              <h1 className="chat-title">{appName}</h1>
              <div className="chat-subtitle">{appTagline}</div>
            </div>
          </div>
          <div className="chat-header-status">
            <div className="status-indicator">
              <span className="status-dot" />
              <span>SYSTEM ONLINE</span>
            </div>
            <span className="status-badge">{selectedProfile?.name || 'ACTIVE'}</span>
          </div>
          <div className="chat-header-actions">
            <TokenUsage usage={sessionUsage} />
            <button className="new-chat-btn" onClick={handleNewChat} type="button">
              NEW CHAT
            </button>
          </div>
        </header>

        {(toolsLoaded.length > 0 || skillsLoaded.length > 0 || searchContext || mcpResults.length > 0) && (
          <AgentCapabilitiesBar
            toolsLoaded={toolsLoaded}
            skillsLoaded={skillsLoaded}
            searchContext={searchContext}
            mcpResults={mcpResults}
          />
        )}

        <div className="chat-messages">
          {messages.length === 0 && selectedProfile && (
            <StarterQuestions
              starters={selectedProfile.starters}
              onSelect={(msg) => handleSend(msg)}
            />
          )}
          {messages.map((msg, i) => (
            <ChatMessage key={i} message={msg} />
          ))}
          <div ref={messagesEndRef} />
        </div>

        {error && error.startsWith('Unauthorized') && (
          <div className="chat-error chat-error--auth">
            <span>{error}</span>
            <button className="login-btn" onClick={logout} type="button">Log In</button>
          </div>
        )}

        <ChatInput onSend={handleSend} disabled={isStreaming} />
        <footer className="classification-footer">
          {classificationBanner}
        </footer>
      </div>
    );
  };

  return (
    <div className="app-layout">
      {!sidebarCollapsed && window.innerWidth <= 768 && (
        <div className="sidebar-backdrop" onClick={toggleSidebar} />
      )}
      <Sidebar
        conversations={conversationIndex}
        activeId={session?.session_id || null}
        isCollapsed={sidebarCollapsed}
        onSelect={handleSelectConversation}
        onDelete={handleDeleteConversation}
        onNewMission={handleNewChat}
        onToggle={toggleSidebar}
        userEmail={user?.email}
        onLogout={logout}
        onOpenAdmin={onOpenAdmin}
      />
      {renderMainContent()}
    </div>
  );
}
