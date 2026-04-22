import { useRef, useState } from 'react';
import { CameraCapture } from './CameraCapture';

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
const MAX_IMAGES = 5;

interface Props {
  images: File[];
  onAdd: (files: File[]) => void;
  onRemove: (index: number) => void;
  disabled: boolean;
}

export function ImageUpload({ images, onAdd, onRemove, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [showCamera, setShowCamera] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    const valid = files.filter((f) => ALLOWED_TYPES.includes(f.type));
    const remaining = MAX_IMAGES - images.length;
    if (remaining > 0 && valid.length > 0) {
      onAdd(valid.slice(0, remaining));
    }
    // Reset input so same file can be re-selected
    if (inputRef.current) inputRef.current.value = '';
  };

  const handleCameraCapture = (file: File) => {
    if (images.length < MAX_IMAGES) {
      onAdd([file]);
    }
    setShowCamera(false);
  };

  return (
    <div className="image-upload">
      {images.map((file, i) => (
        <div key={i} className="image-preview">
          <img src={URL.createObjectURL(file)} alt={file.name} />
          <button
            onClick={() => onRemove(i)}
            type="button"
            disabled={disabled}
            title="Remove"
          >
            ✕
          </button>
        </div>
      ))}
      {images.length < MAX_IMAGES && (
        <div className="image-upload-actions">
          <label className="image-upload-btn">
            <input
              ref={inputRef}
              type="file"
              accept={ALLOWED_TYPES.join(',')}
              multiple
              onChange={handleChange}
              disabled={disabled}
              hidden
            />
            [+]
          </label>
          <button
            type="button"
            className="image-upload-btn camera-toggle-btn"
            onClick={() => setShowCamera(true)}
            disabled={disabled}
          >
            [CAM]
          </button>
        </div>
      )}
      {showCamera && (
        <CameraCapture
          onCapture={handleCameraCapture}
          onClose={() => setShowCamera(false)}
        />
      )}
    </div>
  );
}
