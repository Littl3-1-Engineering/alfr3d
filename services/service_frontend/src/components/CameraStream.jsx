import { useState, useCallback, useEffect, useRef } from 'react';
import { Camera, RefreshCw, AlertTriangle, Image } from 'lucide-react';
import Hls from 'hls.js';
import { API_BASE_URL } from '../config';

const HLS_BASE = `${API_BASE_URL}/api/stream/hls`;
const PLAYLIST_URL = `${HLS_BASE}/index.m3u8`;
const SNAPSHOT_URL = `${API_BASE_URL}/api/stream/camera/snapshot`;

const CameraStream = () => {
  const [status, setStatus] = useState('loading');
  const [showStream, setShowStream] = useState(true);
  const [snapshotUrl, setSnapshotUrl] = useState(null);
  const videoRef = useRef(null);
  const hlsRef = useRef(null);
  const statusRef = useRef('loading');

  const setStatusBoth = useCallback((next) => {
    statusRef.current = next;
    setStatus(next);
  }, []);

  const destroyHls = useCallback(() => {
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }
    const video = videoRef.current;
    if (video) {
      video.removeAttribute('src');
      if (typeof video.load === 'function') video.load();
    }
  }, []);

  const startBackend = useCallback(async () => {
    try {
      const res = await fetch(`${HLS_BASE}/start`, { method: 'POST' });
      return res.ok;
    } catch {
      return false;
    }
  }, []);

  const stopBackend = useCallback(async () => {
    try {
      await fetch(`${HLS_BASE}/stop`, { method: 'POST' });
    } catch {
      // ignore
    }
  }, []);

  const attach = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    destroyHls();
    if (Hls.isSupported()) {
      const hls = new Hls({ liveDurationInfinity: true });
      hlsRef.current = hls;
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        setStatusBoth('connected');
        video.play().catch(() => {});
      });
      hls.on(Hls.Events.ERROR, (_evt, data) => {
        if (data.fatal) {
          setStatusBoth('error');
          destroyHls();
        }
      });
      hls.loadSource(PLAYLIST_URL);
      hls.attachMedia(video);
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = PLAYLIST_URL;
      video.addEventListener('loadedmetadata', () => {
        setStatusBoth('connected');
        video.play().catch(() => {});
      });
    } else {
      setStatusBoth('error');
    }
  }, [destroyHls, setStatusBoth]);

  const connect = useCallback(async () => {
    setStatusBoth('loading');
    destroyHls();
    const ok = await startBackend();
    if (!ok) {
      setStatusBoth('error');
      return;
    }
    attach();
  }, [attach, destroyHls, setStatusBoth, startBackend]);

  useEffect(() => {
    connect();
    return () => {
      destroyHls();
      stopBackend();
    };
  }, [connect, destroyHls, stopBackend]);

  const reconnect = useCallback(() => {
    connect();
  }, [connect]);

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
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              className="w-full h-auto"
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
