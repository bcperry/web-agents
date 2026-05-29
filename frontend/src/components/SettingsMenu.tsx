import { useEffect, useRef, useState } from 'react';

interface SettingsMenuProps {
  userEmail?: string;
  onOpenAdmin: () => void;
  onLogout?: () => void;
}

export function SettingsMenu({ userEmail, onOpenAdmin, onLogout }: SettingsMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    };

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  const handleOpenAdmin = () => {
    setIsOpen(false);
    onOpenAdmin();
  };

  const handleLogout = () => {
    setIsOpen(false);
    onLogout?.();
  };

  return (
    <div className="settings-menu" ref={menuRef}>
      <button
        className="settings-menu-trigger"
        type="button"
        aria-label="Open settings"
        aria-expanded={isOpen}
        aria-haspopup="menu"
        onClick={() => setIsOpen((current) => !current)}
        title="Settings"
      >
        <svg className="settings-menu-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M12 8.25a3.75 3.75 0 1 0 0 7.5 3.75 3.75 0 0 0 0-7.5Zm0 1.5a2.25 2.25 0 1 1 0 4.5 2.25 2.25 0 0 1 0-4.5Z" />
          <path d="M10.7 2.5h2.6l.46 2.38c.58.18 1.13.41 1.64.7l2.02-1.36 1.84 1.84-1.36 2.02c.29.51.52 1.06.7 1.64l2.38.46v2.6l-2.38.46c-.18.58-.41 1.13-.7 1.64l1.36 2.02-1.84 1.84-2.02-1.36c-.51.29-1.06.52-1.64.7l-.46 2.38h-2.6l-.46-2.38a8.42 8.42 0 0 1-1.64-.7l-2.02 1.36-1.84-1.84 1.36-2.02a8.42 8.42 0 0 1-.7-1.64l-2.38-.46v-2.6l2.38-.46c.18-.58.41-1.13.7-1.64L4.74 6.06l1.84-1.84L8.6 5.58c.51-.29 1.06-.52 1.64-.7l.46-2.38Zm1.24 1.5-.39 2.02-.46.11a6.64 6.64 0 0 0-2.08.87l-.4.25-1.72-1.16-.68.68 1.16 1.72-.25.4a6.64 6.64 0 0 0-.87 2.08l-.11.46-2.02.39v.96l2.02.39.11.46c.18.74.47 1.44.87 2.08l.25.4-1.16 1.72.68.68 1.72-1.16.4.25c.64.4 1.34.69 2.08.87l.46.11.39 2.02h.96l.39-2.02.46-.11a6.64 6.64 0 0 0 2.08-.87l.4-.25 1.72 1.16.68-.68-1.16-1.72.25-.4c.4-.64.69-1.34.87-2.08l.11-.46 2.02-.39v-.96l-2.02-.39-.11-.46a6.64 6.64 0 0 0-.87-2.08l-.25-.4 1.16-1.72-.68-.68-1.72 1.16-.4-.25a6.64 6.64 0 0 0-2.08-.87l-.46-.11L12.06 4h-.96Z" />
        </svg>
      </button>

      {isOpen && (
        <div className="settings-menu-panel" role="menu" aria-label="Settings menu">
          <div className="settings-menu-account">
            <div className="settings-menu-label">SIGNED IN</div>
            <div className="settings-menu-email" title={userEmail || 'Unknown user'}>
              {userEmail || 'Unknown user'}
            </div>
          </div>
          <button className="settings-menu-item" type="button" role="menuitem" onClick={handleOpenAdmin}>
            ADMIN
          </button>
          {onLogout && (
            <button className="settings-menu-item logout" type="button" role="menuitem" onClick={handleLogout}>
              LOGOUT
            </button>
          )}
        </div>
      )}
    </div>
  );
}
