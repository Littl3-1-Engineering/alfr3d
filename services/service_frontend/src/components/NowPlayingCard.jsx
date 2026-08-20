import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Disc3, Pause } from 'lucide-react';
import { API_BASE_URL } from '../config';
import socket from '../utils/socket';
import TacticalPanelVariant1 from './TacticalPanelVariant1';

const formatMs = (ms) => {
  if (!ms || ms < 0) return '0:00';
  const total = Math.floor(ms / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
};

const NowPlayingCard = () => {
  const [track, setTrack] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [deviceName, setDeviceName] = useState('');
  const lastTrackIdRef = useRef(null);
  const eventReceivedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    fetch(`${API_BASE_URL}/api/music/spotify/status`)
      .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
      .then((state) => {
        if (cancelled || state?.error || eventReceivedRef.current) return;
        if (state.is_playing && state.item) {
          lastTrackIdRef.current = state.item.id;
          setTrack(state.item);
          setIsPlaying(true);
          setProgress(state.progress_ms || 0);
          setDeviceName(state.device?.name || '');
        } else {
          setTrack(null);
          setIsPlaying(false);
        }
      })
      .catch(() => {});

    const unsubscribe = socket.on('events', (events) => {
      const music = [...(events || [])]
        .reverse()
        .find((event) => event?.type === 'audio' && 'track' in event);
      if (!music) return;
      eventReceivedRef.current = true;
      if (music.is_playing && music.track) {
        lastTrackIdRef.current = music.track.id;
        setTrack(music.track);
        setIsPlaying(true);
        setProgress(music.track.progress_ms || 0);
      } else {
        setTrack(null);
        setIsPlaying(false);
      }
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!isPlaying) return undefined;
    const interval = setInterval(() => {
      setProgress((current) => current + 1000);
    }, 1000);
    return () => clearInterval(interval);
  }, [isPlaying, track?.id]);

  if (!isPlaying || !track) {
    return null;
  }

  const percent = track.duration_ms ? Math.min(100, (progress / track.duration_ms) * 100) : 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <TacticalPanelVariant1 title="N0W PL4Y1NG">
        <div className="flex items-center gap-3">
          <div className="w-14 h-14 shrink-0 rounded border border-fui-border/40 overflow-hidden bg-black/40 flex items-center justify-center">
            {track.album_art ? (
              <img src={track.album_art} alt={track.album || 'Album art'} className="w-full h-full object-cover" />
            ) : (
              <Disc3 className="w-6 h-6 text-fui-text/40" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <Pause className="w-3 h-3 text-fui-accent flex-shrink-0" />
              <p className="text-sm text-fui-text font-mono truncate">{track.name}</p>
            </div>
            <p className="text-xs text-fui-text/70 font-mono truncate">
              {track.artists?.join(', ')}
            </p>
            <p className="text-[10px] text-fui-text/50 font-mono truncate">
              {track.album || ''}
              {deviceName ? ` — ${deviceName}` : ''}
            </p>
          </div>
        </div>
        <div className="mt-3">
          <div className="h-1 bg-fui-border/40 relative overflow-hidden">
            <div
              className="h-full bg-fui-accent"
              style={{ width: `${percent}%`, transition: 'width 1s linear' }}
            />
          </div>
          <div className="flex justify-between text-[10px] text-fui-text/50 font-mono mt-1">
            <span>{formatMs(progress)}</span>
            <span>{formatMs(track.duration_ms)}</span>
          </div>
        </div>
      </TacticalPanelVariant1>
    </motion.div>
  );
};

export default NowPlayingCard;
