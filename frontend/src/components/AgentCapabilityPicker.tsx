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
  return (
    <div className="agent-builder-label">
      {title}
      <span className="agent-builder-tool-desc" style={{ display: 'block', marginBottom: '0.5rem' }}>
        {description}
      </span>
      {loading ? (
        <div className="agent-builder-loading">Loading available {title.toLowerCase()}...</div>
      ) : items.length > 0 ? (
        <div className="agent-builder-tools">
          {items.map((item) => (
            <label key={item.name} className="agent-builder-tool-item">
              <input
                type="checkbox"
                checked={selected.includes(item.name)}
                onChange={() => onToggle(item.name)}
              />
              <span className="agent-builder-tool-name">{nameFormatter(item.name)}</span>
              <span className="agent-builder-tool-desc">{item.description}</span>
            </label>
          ))}
        </div>
      ) : (
        <div className="agent-builder-tool-desc">{emptyText}</div>
      )}
    </div>
  );
}