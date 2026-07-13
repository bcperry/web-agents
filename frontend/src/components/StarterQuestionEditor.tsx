import type { StarterQuestion } from '../types/api';

interface StarterQuestionEditorProps {
  starters: StarterQuestion[];
  newStarterLabel: string;
  newStarterMessage: string;
  onAdd: () => void;
  onRemove: (index: number) => void;
  onUpdate: (index: number, field: keyof StarterQuestion, value: string) => void;
  onLabelChange: (value: string) => void;
  onMessageChange: (value: string) => void;
}

export function StarterQuestionEditor({
  starters,
  newStarterLabel,
  newStarterMessage,
  onAdd,
  onRemove,
  onUpdate,
  onLabelChange,
  onMessageChange,
}: StarterQuestionEditorProps) {
  return (
    <div className="agent-builder-section">
      <h3 className="agent-builder-section-title">STARTER QUESTIONS</h3>
      {starters.length > 0 && (
        <div className="agent-builder-starters-list">
          {starters.map((starter, index) => (
            <div key={index} className="agent-builder-starter-item">
              <input
                className="agent-builder-input"
                type="text"
                value={starter.label}
                onChange={(event) => onUpdate(index, 'label', event.target.value)}
                aria-label={`Starter ${index + 1} button label`}
                maxLength={80}
              />
              <input
                className="agent-builder-input agent-builder-starter-message"
                type="text"
                value={starter.message}
                onChange={(event) => onUpdate(index, 'message', event.target.value)}
                aria-label={`Starter ${index + 1} message`}
                maxLength={500}
              />
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