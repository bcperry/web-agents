import { useMemo, useState } from 'react';
import type { ToolInfo } from '../types/api';

interface AgentCapabilityPickerProps {
  title: string;
  description: string;
  items: ToolInfo[];
  selected: string[];
  loading: boolean;
  emptyText?: string;
  nameFormatter?: (name: string) => string;
  onToggle: (name: string) => void;
}

export function AgentCapabilityPicker({
  title,
  description,
  items,
  selected,
  loading,
  emptyText = 'No items available',
  nameFormatter = (name) => name,
  onToggle,
}: AgentCapabilityPickerProps) {
  const [expanded, setExpanded] = useState(selected.length > 0);
  const [query, setQuery] = useState('');

  const visibleItems = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return [...items]
      .sort((a, b) => Number(selected.includes(b.name)) - Number(selected.includes(a.name)))
      .filter((item) => !normalizedQuery || `${item.name} ${item.description}`.toLowerCase().includes(normalizedQuery));
  }, [items, query, selected]);

  return (
    <div className="agent-builder-section agent-builder-capability-section">
      <button
        className="agent-builder-capability-header"
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        <span className="agent-builder-section-title">{title}</span>
        <span className="agent-builder-capability-summary">
          {selected.length} selected
          <span aria-hidden="true">{expanded ? '−' : '+'}</span>
        </span>
      </button>
      {expanded && (
        <div className="agent-builder-capability-content">
          <span className="agent-builder-tool-desc">{description}</span>
          {items.length > 8 && (
            <input
              className="agent-builder-input agent-builder-capability-search"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={`Search ${title.toLowerCase()}`}
              aria-label={`Search ${title.toLowerCase()}`}
            />
          )}
          {loading ? (
            <div className="agent-builder-loading">Loading available {title.toLowerCase()}...</div>
          ) : items.length > 0 ? (
            <div className="agent-builder-tools">
              {visibleItems.map((item) => (
                <label key={item.name} className="agent-builder-tool-item" title={item.description}>
                  <input
                    type="checkbox"
                    checked={selected.includes(item.name)}
                    onChange={() => onToggle(item.name)}
                  />
                  <span className="agent-builder-tool-name">{nameFormatter(item.name)}</span>
                </label>
              ))}
              {visibleItems.length === 0 && <div className="agent-builder-tool-desc">No matches</div>}
            </div>
          ) : (
            <div className="agent-builder-tool-desc">{emptyText}</div>
          )}
        </div>
      )}
    </div>
  );
}