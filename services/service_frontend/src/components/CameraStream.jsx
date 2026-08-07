import { useState, useCallback, useEffect, useRef } from 'react';
import { Camera, RefreshCw, AlertTriangle, Image } from 'lucide-react';
import { API_BASE_URL } from '../config';

const SNAPSHOT_URL = `${API_BASE_URL}/api/stream/camera/snapshot`;

const CameraStream = () => {
  const [status, setStatus] = useState('loading');
  const [showStream, setShowStream] = useState(true);
  const [snapshotUrl, setSnapshotUrl] = useState(null);
  const intervalRef = useRef(null);
  const imgRef = useRef(null);
  const statusRef = useRef('loading');

  const scheduleNextRef = useRef(null);

  const cleanup = useCallback(() => {
    if (scheduleNextRef.current) clearTimeout(scheduleNextRef.current);
    scheduleNextRef.current = null;
  }, []);

  const scheduleNext = useCallback(() => {
    cleanup();
    scheduleNextRef.current = setTimeout(() => {
      if (imgRef.current) {
        imgRef.current.src = `${SNAPSHOT_URL}?_=${Date.now()}`;
      }
    }, 500);
  }, [cleanup]);

  const startPolling = useCallback(() => {
    cleanup();
    statusRef.current = 'loading';
    setStatus('loading');
    if (imgRef.current) {
      imgRef.current.src = `${SNAPSHOT_URL}?_=${Date.now()}`;
    }
  }, [cleanup]);

  useEffect(() => {
    startPolling();
    return () => cleanup();
  }, [startPolling, cleanup]);

  const reconnect = useCallback(() => {
    startPolling();
  }, [startPolling]);

  const handleLoad = () => {
    if (statusRef.current === 'loading') {
      setStatus('connected');
      statusRef.current = 'connected';
    }
    scheduleNext();
  };

  const handleError = () => {
    setStatus('error');
    statusRef.current = 'error';
  };

  const captureSnapshot = async () => {
    try {
      const res = await fetch(SNAPSHOT_URL);
      if (!res.ok) return;
      const blob = await res.blob();
      setSnapshotUrl(URL.createObjectURL(blob));
    } catch {
      return;
    }
  };

  const clearSnapshot = () => {
    if (snapshotUrl) URL.revokeObjectURL(snapshotUrl);
    setSnapshotUrl(null);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between border-b border-fui-border pb-2 mb-2">
        <div className="flex items-center gap-2">
          <Camera size={14} className="text-fui-accent" />
          <span className="font-tech text-xs uppercase text-fui-text">CAM3RA F33D</span>
          <span className={`inline-block w-1.5 h-1.5 rounded-full ${
            status === 'connected' ? 'bg-green-500' :
            status === 'loading' ? 'bg-yellow-500 animate-pulse' : 'bg-red-500'
          }`} />
          <span className="text-[10px] font-mono uppercase text-fui-text/60">
            {status === 'connected' ? 'LIV3' :
             status === 'loading' ? 'CNCT1NG...' : '3RR0R'}
          </span>
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => setShowStream(s => !s)}
            className="px-1.5 py-0.5 border border-fui-border text-fui-text/60 hover:text-fui-accent hover:border-fui-accent transition-colors"
            title={showStream ? 'Hide stream' : 'Show stream'}
          >
            {showStream ? 'H1D3' : 'SH0W'}
          </button>
          <button
            onClick={captureSnapshot}
            className="px-1.5 py-0.5 border border-fui-border text-fui-text/60 hover:text-fui-accent hover:border-fui-accent transition-colors"
            title="Capture snapshot"
          >
            <Image size={11} />
          </button>
          <button
            onClick={reconnect}
            className="px-1.5 py-0.5 border border-fui-border text-fui-text/60 hover:text-fui-accent hover:border-fui-accent transition-colors"
            title="Reconnect"
          >
            <RefreshCw size={11} />
          </button>
        </div>
      </div>

      {snapshotUrl && (
        <div className="relative">
          <img
            src={snapshotUrl}
            alt="Camera snapshot"
            className="w-full border border-fui-border"
          />
          <button
            onClick={clearSnapshot}
            className="absolute top-1 right-1 px-1.5 py-0.5 bg-black/70 border border-fui-border text-fui-text text-[10px] hover:text-fui-accent"
          >
            CL0S3
          </button>
        </div>
      )}

      {showStream ? (
        status === 'error' ? (
          <div className="flex flex-col items-center justify-center py-8 border border-fui-border bg-black/20">
            <AlertTriangle size={24} className="text-red-500 mb-2" />
            <p className="font-mono text-xs text-fui-text/60 mb-3">STR3AM UNR34CH4BL3</p>
            <button
              onClick={reconnect}
              className="px-3 py-1 border border-fui-accent text-fui-accent font-mono text-xs uppercase hover:bg-fui-accent hover:text-black transition-colors"
            >
              R3TRY
            </button>
          </div>
        ) : (
          <div className="relative border border-fui-border bg-black/40">
            <img
              ref={imgRef}
              alt="Camera stream"
              className="w-full h-auto"
              onLoad={handleLoad}
              onError={handleError}
              style={{ minHeight: '120px' }}
            />
            {status === 'loading' && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/60">
                <div className="flex flex-col items-center gap-2">
                  <RefreshCw size={20} className="text-fui-accent animate-spin" />
                  <span className="font-mono text-[10px] text-fui-text/60 uppercase">C0NN3CT1NG T0 C4M3R4...</span>
                </div>
              </div>
            )}
          </div>
        )
      ) : (
        <div className="flex items-center justify-center py-6 border border-fui-border bg-black/20">
          <p className="font-mono text-xs text-fui-text/60">STR3AM H1DD3N</p>
        </div>
      )}
    </div>
  );
};

export default CameraStream;
