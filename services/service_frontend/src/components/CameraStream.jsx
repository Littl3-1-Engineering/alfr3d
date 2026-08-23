import { useState, useCallback, useEffect, useRef } from 'react';
import { Camera, RefreshCw, AlertTriangle, Image } from 'lucide-react';
import Hls from 'hls.js';
import { API_BASE_URL } from '../config';
import { apiFetch } from '../utils/apiClient';

const STREAM_BASE = `${API_BASE_URL}/api/stream`;
const hlsBase = (id) => `${STREAM_BASE}/hls/${id}`;
const playlistUrl = (id) => `${hlsBase(id)}/index.m3u8`;
const snapshotUrl = (id) => `${STREAM_BASE}/camera/${id}/snapshot`;

const CameraStream = () => {
  const [cameras, setCameras] = useState(null);
  const [selectedCameraId, setSelectedCameraId] = useState(null);
  const [status, setStatus] = useState('loading');
  const [showStream, setShowStream] = useState(true);
  const [snapshot, setSnapshot] = useState(null);
  const videoRef = useRef(null);
  const hlsRef = useRef(null);

  useEffect(() => {
    fetch(`${STREAM_BASE}/cameras`)
      .then((r) => (r.ok ? r.json() : []))
      .then((list) => {
        setCameras(list);
        setSelectedCameraId((prev) => prev ?? list[0]?.id ?? null);
      })
      .catch(() => setCameras([]));
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

  const startBackend = useCallback(async (id) => {
    try {
      const res = await apiFetch(`${hlsBase(id)}/start`, { method: 'POST' });
      return res.ok;
    } catch {
      return false;
    }
  }, []);

  const stopBackend = useCallback(async (id) => {
    try {
      await apiFetch(`${hlsBase(id)}/stop`, { method: 'POST' });
    } catch {
      // ignore
    }
  }, []);

  const attach = useCallback(
    (id) => {
      const video = videoRef.current;
      if (!video) return;
      destroyHls();
      if (Hls.isSupported()) {
        const hls = new Hls({ liveDurationInfinity: true });
        hlsRef.current = hls;
        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          setStatus('connected');
          video.play().catch(() => {});
        });
        hls.on(Hls.Events.ERROR, (_evt, data) => {
          if (data.fatal) {
            setStatus('error');
            destroyHls();
          }
        });
        hls.loadSource(playlistUrl(id));
        hls.attachMedia(video);
      } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        video.src = playlistUrl(id);
        video.addEventListener('loadedmetadata', () => {
          setStatus('connected');
          video.play().catch(() => {});
        });
      } else {
        setStatus('error');
      }
    },
    [destroyHls]
  );

  const connect = useCallback(
    async (id) => {
      if (!id) return;
      setStatus('loading');
      destroyHls();
      const ok = await startBackend(id);
      if (!ok) {
        setStatus('error');
        return;
      }
      attach(id);
    },
    [attach, destroyHls, startBackend]
  );

  useEffect(() => {
    if (!selectedCameraId) return;
    connect(selectedCameraId);
    return () => {
      destroyHls();
      stopBackend(selectedCameraId);
    };
  }, [selectedCameraId, connect, destroyHls, stopBackend]);

  const reconnect = useCallback(() => {
    if (selectedCameraId) connect(selectedCameraId);
  }, [connect, selectedCameraId]);

  const selectCamera = (id) => {
    if (id === selectedCameraId) return;
    setSelectedCameraId(id);
  };

  const captureSnapshot = async () => {
    if (!selectedCameraId) return;
    try {
      const res = await fetch(snapshotUrl(selectedCameraId));
      if (!res.ok) return;
      const blob = await res.blob();
      setSnapshot(URL.createObjectURL(blob));
    } catch {
      return;
    }
  };

  const clearSnapshot = () => {
    if (snapshot) URL.revokeObjectURL(snapshot);
    setSnapshot(null);
  };

  const noCameras = cameras !== null && cameras.length === 0;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between border-b border-fui-border pb-2 mb-2">
        <div className="flex items-center gap-2">
          <Camera size={14} className="text-fui-accent" />
          <span className="font-tech text-xs uppercase text-fui-text">CAM3RA F33D</span>
          {!noCameras && (
            <>
              <span
                className={`inline-block w-1.5 h-1.5 rounded-full ${
                  status === 'connected'
                    ? 'bg-green-500'
                    : status === 'loading'
                      ? 'bg-yellow-500 animate-pulse'
                      : 'bg-red-500'
                }`}
              />
              <span className="text-[10px] font-mono uppercase text-fui-text/60">
                {status === 'connected' ? 'LIV3' : status === 'loading' ? 'CNCT1NG...' : '3RR0R'}
              </span>
            </>
          )}
        </div>
        {!noCameras && (
          <div className="flex gap-1">
            <button
              onClick={() => setShowStream((s) => !s)}
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
        )}
      </div>

      {cameras && cameras.length > 1 && (
        <div className="flex flex-wrap gap-1">
          {cameras.map((cam) => (
            <button
              key={cam.id}
              onClick={() => selectCamera(cam.id)}
              className={`px-2 py-0.5 border font-mono text-[10px] uppercase transition-colors ${
                cam.id === selectedCameraId
                  ? 'border-fui-accent text-fui-accent bg-fui-accent/10'
                  : 'border-fui-border text-fui-text/60 hover:text-fui-accent hover:border-fui-accent'
              }`}
            >
              {cam.name}
            </button>
          ))}
        </div>
      )}

      {snapshot && (
        <div className="relative">
          <img src={snapshot} alt="Camera snapshot" className="w-full border border-fui-border" />
          <button
            onClick={clearSnapshot}
            className="absolute top-1 right-1 px-1.5 py-0.5 bg-black/70 border border-fui-border text-fui-text text-[10px] hover:text-fui-accent"
          >
            CL0S3
          </button>
        </div>
      )}

      {noCameras ? (
        <div className="flex flex-col items-center justify-center py-8 border border-fui-border bg-black/20">
          <Camera size={24} className="text-fui-text/30 mb-2" />
          <p className="font-mono text-xs text-fui-text/60">N0 C4M3R4S C0NF1GUR3D</p>
        </div>
      ) : showStream ? (
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
