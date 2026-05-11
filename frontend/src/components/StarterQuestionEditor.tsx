import type { StarterQuestion } from '../types/api';

interface StarterQuestionEditorProps {
  starters: StarterQuestion[];
  newStarterLabel: string;
  newStarterMessage: string;
  onAdd: () => void;
  onRemove: (index: number) => void;
  onLabelChange: (value: string) => void;
  onMessageChange: (value: string) => void;
}

export function StarterQuestionEditor({
  starters,
  newStarterLabel,
  newStarterMessage,
  onAdd,
  onRemove,
  onLabelChange,
  onMessageChange,
}: StarterQuestionEditorProps) {
  return (
    <div className="agent-builder-label">
      STARTER QUESTIONS
      {starters.length > 0 && (
        <div className="agent-builder-starters-list">
          {starters.map((starter, index) => (
            <div key={index} className="agent-builder-starter-item">
              <span className="agent-builder-starter-label">{starter.label}</span>
              <button onClick={() => onRemove(index)} type="button" title="Remove">x</button>
            </div>
          ))}
        </div>
      )}
      <div className="agent-builder-starter-add">
        <input
          className="agent-builder-input"
          type="text"
          value={newStarterLabel}
          onChange={(event) => onLabelChange(event.target.value)}
          placeholder="Button label"
          maxLength={80}
        />
        <input
          className="agent-builder-input"
          type="text"
          value={newStarterMessage}
          onChange={(event) => onMessageChange(event.target.value)}
          placeholder="Message to send"
          maxLength={500}
        />
        <button
          className="agent-builder-starter-add-btn"
          onClick={onAdd}
          type="button"
          disabled={!newStarterLabel.trim() || !newStarterMessage.trim()}
        >
          + ADD
        </button>
      </div>
    </div>
  );
}