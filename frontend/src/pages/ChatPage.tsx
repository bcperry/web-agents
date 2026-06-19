import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import type { AgentCustomizationOverride, AgentProfile, ConversationIndexEntry } from '../types/api';
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
import { SettingsMenu } from '../components/SettingsMenu';
import { getRuntimeConfigSnapshot } from '../config/runtimeConfig';
import type { CustomAgentDefinition } from '../types/api';

interface ChatPageProps {
  onOpenAdmin: () => void;
  onOpenAutonomous: () => void;
  customAgents: CustomAgentDefinition[];
  builtInOverrides: AgentCustomizationOverride[];
}

const SPINNER_MESSAGES = [
  'INITIALIZING AGENT RUNTIME...',
  'ESTABLISHING SECURE CONNECTION...',
  'LOADING MISSION PARAMETERS...',
  'FINDING THE T-1000...',
];

// Sentinel agent card that links to the dedicated Duty Officer (autonomous)
// console instead of starting a normal chat session.
const DUTY_OFFICER_PROFILE_ID = '__duty_officer__';

const DUTY_OFFICER_PROFILE: AgentProfile = {
  id: DUTY_OFFICER_PROFILE_ID,
  name: 'Duty Officer',
  description:
    'Autonomous chief of staff. Monitors activity on a schedule and reports what needs your attention.',
  icon: '/icons/hybrid.svg',
  group: 'Automations',
  starters: [],
};

export function ChatPage({ onOpenAdmin, onOpenAutonomous, customAgents, builtInOverrides }: ChatPageProps) {
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

  const {
    messages,
    isStreaming,
    session,
    sessionUsage,
    mcpResults,
    toolsLoaded,
    skillsLoaded,
    agentsLoaded,
    searchContext,
    error,
    saveCounter,
    startSession,
    endSession,
    send,
    saveCurrentConversation,
  } = useChat();

  const { loadIndex, deleteConversation } = useConversationStore();
  const { user, logout, classificationBanner } = useAuth();
  const { setActiveAgentId } = useTheme();
  const { appName, appTagline, appLogo } = getRuntimeConfigSnapshot();

  // Merge server profiles with custom agents
  const allProfiles: AgentProfile[] = useMemo(() => [
    ...profiles.map((profile) => {
      const override = builtInOverrides.find((item) => item.baseProfileId === profile.id);
      return override
        ? {
            ...profile,
            isCustomized: true,
            builtInOverride: override,
            overrideUpdatedAt: override.updatedAt,
            starters: override.starters.length > 0 ? override.starters : profile.starters,
          }
        : profile;
    }),
    ...customAgents.map((a) => ({
      id: a.id,
      name: a.name,
      description: a.description,
      icon: a.icon,
      starters: a.starters,
      isCustom: true as const,
      customAgent: a,
    })),
    DUTY_OFFICER_PROFILE,
  ], [builtInOverrides, customAgents, profiles]);

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
    void loadIndex().then(setConversationIndex);
  }, [loadIndex]);

  // Refresh conversation index whenever a save completes
  useEffect(() => {
    if (saveCounter > 0) {
      void loadIndex().then(setConversationIndex);
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
    // The Duty Officer card is a shortcut into the dedicated autonomous console,
    // not a regular chat session.
    if (profileId === DUTY_OFFICER_PROFILE_ID) {
      onOpenAutonomous();
      return;
    }
    const profile = allProfiles.find((p) => p.id === profileId);
    if (profile) {
      setSelectedProfile(profile);
      setCreatingSession(true);
      setSpinnerTextIndex(0);
      try {
        await startSession(profile);
        // Push a history entry so the back button returns to profile selection.
        window.history.pushState({ view: 'chat-active' }, '');
      } finally {
        setCreatingSession(false);
      }
    }
  }, [allProfiles, startSession, onOpenAutonomous]);

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
      void loadIndex().then(setConversationIndex);
      // Replace the chat-active history entry with a chat entry so the back
      // button doesn't try to re-enter a session that no longer exists.
      if ((window.history.state as { view?: string } | null)?.view === 'chat-active') {
        window.history.replaceState({ view: 'chat' }, '');
      }
    } finally {
      isEndingSessionRef.current = false;
    }
  }, [saveCurrentConversation, endSession, loadIndex]);

  // Handle browser back/forward button navigation for active sessions.
  useEffect(() => {
    const handlePopState = (e: PopStateEvent) => {
      const view = (e.state as { view?: string } | null)?.view;
      if (view === 'chat' && session && !isEndingSessionRef.current) {
        // Back from active session → end it and return to profile selection.
        void handleNewChat();
      } else if (view === 'chat-active' && !session) {
        // Forward into an expired session → neutralize the stale history entry.
        window.history.replaceState({ view: 'chat' }, '');
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [session, handleNewChat]);

  const handleSelectConversation = useCallback(async (id: string) => {
    // End the current session so the UI transitions to the spinner state.
    if (session) {
      await endSession();
    }

    const entry = conversationIndex.find((e) => e.id === id);
    if (!entry) return;

    // Custom-agent chats are stored with profileId "custom"; resolve them by
    // customAgentId so the full definition is re-inlined on resume.
    const profile = entry.profileId === 'custom' && entry.customAgentId
      ? allProfiles.find((p) => p.customAgent?.id === entry.customAgentId)
      : allProfiles.find((p) => p.id === entry.profileId);
    setSelectedProfile(profile || null);
    setCreatingSession(true);
    setSpinnerTextIndex(0);

    // On mobile, close sidebar after selection
    if (window.innerWidth <= 768) {
      setSidebarCollapsed(true);
    }

    try {
      await startSession(profile || {
        id: entry.profileId,
        name: entry.profileName,
        description: entry.description,
        icon: '/icons/custom.svg',
        starters: [],
      }, entry);
      // Push a history entry so the back button returns to profile selection,
      // but only if we're not already in an active session (switching conversations
      // should not add an extra back step).
      if ((window.history.state as { view?: string } | null)?.view !== 'chat-active') {
        window.history.pushState({ view: 'chat-active' }, '');
      }
    } finally {
      setCreatingSession(false);
    }
  }, [session, conversationIndex, allProfiles, startSession, endSession]);

  const handleDeleteConversation = useCallback(async (id: string) => {
    try {
      await deleteConversation(id);
    } catch {
      /* surfaced by the API layer */
    }
    void loadIndex().then(setConversationIndex);
  }, [deleteConversation, loadIndex]);

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((prev) => !prev);
  }, []);

  const renderSettingsMenu = () => (
    <SettingsMenu userEmail={user?.email} onOpenAdmin={onOpenAdmin} onLogout={logout} />
  );

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
            <div className="chat-header-actions">
              {renderSettingsMenu()}
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
            {renderSettingsMenu()}
          </div>
        </header>

        {(toolsLoaded.length > 0 || skillsLoaded.length > 0 || agentsLoaded.length > 0 || searchContext || mcpResults.length > 0 || selectedProfile?.isCustomized) && (
          <AgentCapabilitiesBar
            toolsLoaded={toolsLoaded}
            skillsLoaded={skillsLoaded}
            agentsLoaded={agentsLoaded}
            searchContext={searchContext}
            mcpResults={mcpResults}
            isCustomized={selectedProfile?.isCustomized}
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
      />
      {renderMainContent()}
    </div>
  );
}
