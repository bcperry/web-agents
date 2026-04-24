import type { ConversationIndexEntry } from '../types/api';
import { useTheme, type ThemeMode } from '../hooks/useTheme';

const THEME_OPTIONS: { value: ThemeMode; label: string }[] = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
];

interface SidebarProps {
  conversations: ConversationIndexEntry[];
  activeId: string | null;
  isCollapsed: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onNewMission: () => void;
  onToggle: () => void;
  userEmail?: string;
  onLogout?: () => void;
  onOpenAdmin?: () => void;
}

function formatDate(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) +
    ' ' + date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
}

export function Sidebar({
  conversations,
  activeId,
  isCollapsed,
  onSelect,
  onDelete,
  onNewMission,
  onToggle,
  userEmail,
  onLogout,
  onOpenAdmin,
}: SidebarProps) {
  const { mode, setMode } = useTheme();

  return (
    <div className={`sidebar ${isCollapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-header">
        <button className="sidebar-toggle" onClick={onToggle} type="button" title="Toggle sidebar">
          ☰
        </button>
        {!isCollapsed && (
          <button className="sidebar-new-mission" onClick={onNewMission} type="button">
            + NEW CHAT
          </button>
        )}
      </div>

      {!isCollapsed && (
        <div className="sidebar-list">
          {conversations.length === 0 ? (
            <div className="sidebar-empty">No past conversations</div>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.id}
                className={`sidebar-entry ${conv.id === activeId ? 'active' : ''}`}
                onClick={() => onSelect(conv.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => { if (e.key === 'Enter') onSelect(conv.id); }}
              >
                <div className="sidebar-entry-content">
                  <div className="sidebar-entry-description">{conv.description}</div>
                  <div className="sidebar-entry-meta">
                    <span className="sidebar-entry-profile">{conv.profileName}</span>
                    <span className="sidebar-entry-date">{formatDate(conv.lastActivityAt)}</span>
                  </div>
                </div>
                <button
                  className="sidebar-entry-delete"
                  onClick={(e) => { e.stopPropagation(); onDelete(conv.id); }}
                  type="button"
                  title="Delete conversation"
                >
                  🗑
                </button>
              </div>
            ))
          )}
        </div>
      )}

      {!isCollapsed && (
        <div className="sidebar-theme-selector">
          <div className="sidebar-theme-label">THEME</div>
          <div className="sidebar-theme-options">
            {THEME_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                className={`sidebar-theme-btn ${mode === opt.value ? 'active' : ''}`}
                onClick={() => setMode(opt.value)}
                type="button"
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {!isCollapsed && (onOpenAdmin || onLogout || userEmail) && (
        <div className="sidebar-advanced">
          <div className="sidebar-advanced-label">ADVANCED</div>
          {onOpenAdmin && (
            <button className="sidebar-advanced-btn" onClick={onOpenAdmin} type="button">
              ⚙ ADMIN
            </button>
          )}
          {userEmail && <div className="sidebar-advanced-email" title={userEmail}>{userEmail}</div>}
          {onLogout && (
            <button className="sidebar-advanced-btn logout" onClick={onLogout} type="button">
              ↪ LOGOUT
            </button>
          )}
        </div>
      )}
    </div>
  );
}
