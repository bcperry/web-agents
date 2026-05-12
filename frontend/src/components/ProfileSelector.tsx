import { useEffect, useMemo, useRef, useState } from 'react';
import type { AgentProfile } from '../types/api';

interface Props {
  profiles: AgentProfile[];
  onSelect: (profileId: string) => void;
}

const OTHER_GROUP = 'Other';
const MIN_PAGE_SIZE = 6;

function getGroupName(profile: AgentProfile): string {
  const name = profile.group ?? profile.customAgent?.group ?? profile.builtInOverride?.group ?? '';
  return name.trim() || OTHER_GROUP;
}

export function ProfileSelector({ profiles, onSelect }: Props) {
  const grouped = useMemo(() => {
    const groups: Record<string, AgentProfile[]> = {};
    for (const profile of profiles) {
      const groupName = getGroupName(profile);
      (groups[groupName] ??= []).push(profile);
    }
    // Sort group names alphabetically, with "Other" always last
    const orderedNames = Object.keys(groups).sort((a, b) => {
      if (a === OTHER_GROUP) return 1;
      if (b === OTHER_GROUP) return -1;
      return a.localeCompare(b);
    });
    return orderedNames.map((name) => ({ name, profiles: groups[name] }));
  }, [profiles]);

  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [columnCount, setColumnCount] = useState<number>(1);
  const groupsContainerRef = useRef<HTMLDivElement | null>(null);

  // Measure column count by computing how many ~220px (flex-basis) cards fit in
  // the parent container's width with the gap. The parent is always mounted, so
  // collapse/expand of individual groups never breaks measurement.
  useEffect(() => {
    const el = groupsContainerRef.current;
    if (!el) return;
    const CARD_BASIS = 220; // matches flex: 0 1 220px in CSS
    const update = () => {
      const containerWidth = el.clientWidth;
      if (containerWidth === 0) return;
      // Inner section padding (16px each side) reduces effective width by 32.
      const effectiveWidth = Math.max(0, containerWidth - 32);
      const gap = 16;
      const count = Math.max(1, Math.floor((effectiveWidth + gap) / (CARD_BASIS + gap)));
      setColumnCount((prev) => (prev === count ? prev : count));
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const pageSize = useMemo(() => {
    return Math.max(columnCount, Math.ceil(MIN_PAGE_SIZE / columnCount) * columnCount);
  }, [columnCount]);

  const toggleCollapse = (groupName: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupName)) {
        next.delete(groupName);
      } else {
        next.add(groupName);
      }
      return next;
    });
  };

  const expandGroup = (groupName: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      next.add(groupName);
      return next;
    });
  };

  return (
    <div className="profile-selector">
      <h2 className="profile-selector-title">SELECT YOUR AGENT</h2>
      <div className="profile-selector-groups" ref={groupsContainerRef}>
        {grouped.map(({ name: groupName, profiles: groupProfiles }) => {
          const isCollapsed = collapsedGroups.has(groupName);
          const isExpanded = expandedGroups.has(groupName);
          const visibleProfiles = isExpanded ? groupProfiles : groupProfiles.slice(0, pageSize);
          const remaining = groupProfiles.length - visibleProfiles.length;

          return (
            <section
              key={groupName}
              className={`profile-selector-group${isCollapsed ? ' collapsed' : ''}`}
            >
              <button
                className="agent-builder-section-toggle profile-selector-group-toggle"
                type="button"
                aria-expanded={!isCollapsed}
                onClick={() => toggleCollapse(groupName)}
              >
                <span className="agent-builder-section-title profile-selector-group-title">
                  {groupName.toUpperCase()} ({groupProfiles.length})
                </span>
                <span className="agent-builder-section-toggle-icon" aria-hidden="true">
                  {isCollapsed ? '+' : '-'}
                </span>
              </button>
              {!isCollapsed && (
                <>
                  <div className="profile-cards">
                    {visibleProfiles.map((profile) => (
                      <button
                        key={profile.id}
                        className="profile-card"
                        onClick={() => onSelect(profile.id)}
                        type="button"
                      >
                        <img
                          className="profile-card-icon"
                          src={profile.icon}
                          alt={profile.name}
                          onError={(e) => {
                            (e.target as HTMLImageElement).style.display = 'none';
                          }}
                        />
                        <div className="profile-card-name">{profile.name}</div>
                        <div className="profile-card-desc">{profile.description}</div>
                        {profile.isCustomized && (
                          <span className="profile-card-badge profile-card-badge--customized">CUSTOMIZED</span>
                        )}
                        {profile.isCustom && <span className="profile-card-badge">CUSTOM</span>}
                      </button>
                    ))}
                  </div>
                  {remaining > 0 && (
                    <button
                      className="profile-selector-show-more"
                      type="button"
                      onClick={() => expandGroup(groupName)}
                    >
                      SHOW MORE ({remaining} REMAINING)
                    </button>
                  )}
                </>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
