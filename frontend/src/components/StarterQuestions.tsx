import type { StarterQuestion } from '../types/api';

interface Props {
  starters: StarterQuestion[];
  onSelect: (message: string) => void;
}

export function StarterQuestions({ starters, onSelect }: Props) {
  if (starters.length === 0) return null;

  return (
    <div className="starter-questions">
      <div className="starter-questions-label">SUGGESTED QUERIES</div>
      <div className="starter-questions-list">
        {starters.map((starter, i) => (
          <button
            key={i}
            className="starter-question-btn"
            onClick={() => onSelect(starter.message)}
            type="button"
          >
            {'► ' + starter.label}
          </button>
        ))}
      </div>
    </div>
  );
}
