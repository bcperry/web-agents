import { useRef, useState, useCallback, useEffect } from 'react';

interface Props {
  onCapture: (file: File) => void;
  onClose: () => void;
}

export function CameraCapture({ onCapture, onClose }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  const stopStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } } })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.onloadedmetadata = () => setReady(true);
        }
      })
      .catch(() => {
        if (!cancelled) setError('Camera access denied or unavailable');
      });

    return () => {
      cancelled = true;
      stopStream();
    };
  }, [stopStream]);

  const handleCapture = () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.drawImage(video, 0, 0);

    canvas.toBlob(
      (blob) => {
        if (blob) {
          const file = new File([blob], `capture-${Date.now()}.jpg`, { type: 'image/jpeg' });
          stopStream();
          onCapture(file);
        }
      },
      'image/jpeg',
      0.9,
    );
  };

  const handleClose = () => {
    stopStream();
    onClose();
  };

  return (
    <div className="camera-overlay">
      <div className="camera-container">
        {error ? (
          <div className="camera-error">{error}</div>
        ) : (
          <video ref={videoRef} autoPlay playsInline muted className="camera-preview" />
        )}
        <canvas ref={canvasRef} hidden />
        <div className="camera-controls">
          <button type="button" className="camera-btn camera-cancel" onClick={handleClose}>
            CANCEL
          </button>
          {ready && !error && (
            <button type="button" className="camera-btn camera-capture" onClick={handleCapture}>
              CAPTURE
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
