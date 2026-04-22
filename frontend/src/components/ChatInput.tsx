import { useState, type FormEvent, type KeyboardEvent } from 'react';
import { ImageUpload } from './ImageUpload';

interface Props {
  onSend: (content: string, images?: File[]) => void;
  disabled: boolean;
  maxLength?: number;
}

const DEFAULT_MAX_LENGTH = 8000;

export function ChatInput({ onSend, disabled, maxLength = DEFAULT_MAX_LENGTH }: Props) {
  const [text, setText] = useState('');
  const [images, setImages] = useState<File[]>([]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed, images.length > 0 ? images : undefined);
    setText('');
    setImages([]);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as unknown as FormEvent);
    }
  };

  const overLimit = text.length > maxLength;

  return (
    <form className="chat-input-form" onSubmit={handleSubmit}>
      <ImageUpload
        images={images}
        onAdd={(files) => setImages((prev) => [...prev, ...files])}
        onRemove={(i) => setImages((prev) => prev.filter((_, idx) => idx !== i))}
        disabled={disabled}
      />
      <div className="chat-input-container">
        <textarea
          className="chat-input-textarea"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your message..."
          disabled={disabled}
          rows={1}
        />
        <button
          className="chat-input-send"
          type="submit"
          disabled={disabled || !text.trim() || overLimit}
        >
          TRANSMIT
        </button>
      </div>
      {overLimit && (
        <div className="chat-input-warning">
          Message exceeds {maxLength.toLocaleString()} character limit ({text.length.toLocaleString()})
        </div>
      )}
    </form>
  );
}
