import { useEffect, useRef } from 'react';
import PropTypes from 'prop-types';
import { API_BASE_URL } from '../config';

const BAR_COUNT = 56;
const WINDOW_SEC = 6;
const LOUD_MIN = -50;
const LOUD_RANGE = 50;
const analysisCache = new Map();

const loudnessToHeight = (db) => {
  if (db == null) return 0.06;
  const h = (db - LOUD_MIN) / LOUD_RANGE;
  return Math.min(1, Math.max(0.06, h));
};

const findSegment = (segments, t) => {
  let lo = 0;
  let hi = segments.length - 1;
  let idx = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (segments[mid].start <= t) {
      idx = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return idx >= 0 ? segments[idx] : null;
};

const AudioVisualizer = ({ trackId, isPlaying, progressMs }) => {
  const barRefs = useRef([]);
  const segmentsRef = useRef(null);
  const frameRef = useRef(null);
  const progressRef = useRef(0);
  const lastPollRef = useRef(performance.now());
  const playingRef = useRef(false);

  progressRef.current = progressMs;
  playingRef.current = isPlaying;
  lastPollRef.current = performance.now();

  useEffect(() => {
    let cancelled = false;
    segmentsRef.current = null;
    if (!trackId) return undefined;

    if (analysisCache.has(trackId)) {
      segmentsRef.current = analysisCache.get(trackId);
      return undefined;
    }

    fetch(`${API_BASE_URL}/api/music/spotify/audio-analysis/${trackId}`)
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((data) => {
        if (cancelled) return;
        const segs = (data.segments || []).map((s) => ({
          start: s[0],
          dur: s[1],
          lmax: s[3],
        }));
        analysisCache.set(trackId, segs);
        segmentsRef.current = segs;
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [trackId]);

  useEffect(() => {
    const renderBars = (segments, posSec) => {
      for (let i = 0; i < BAR_COUNT; i++) {
        const t = posSec + ((i / BAR_COUNT) - 0.5) * WINDOW_SEC;
        const seg = findSegment(segments, t);
        const height = seg ? loudnessToHeight(seg.lmax) : 0.06;
        const el = barRefs.current[i];
        if (el) el.style.height = `${Math.round(height * 100)}%`;
      }
    };

    const renderIdle = (now) => {
      for (let i = 0; i < BAR_COUNT; i++) {
        const h = 0.12 + 0.18 * Math.abs(Math.sin(now * 0.0018 + i * 0.35));
        const el = barRefs.current[i];
        if (el) el.style.height = `${Math.round(h * 100)}%`;
      }
    };

    const loop = (now) => {
      const posSec = playingRef.current
        ? (progressRef.current + (now - lastPollRef.current)) / 1000
        : progressRef.current / 1000;
      const segments = segmentsRef.current;
      if (segments && segments.length) {
        renderBars(segments, posSec);
      } else {
        renderIdle(now);
      }
      frameRef.current = requestAnimationFrame(loop);
    };

    frameRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frameRef.current);
  }, []);

  return (
    <div
      className="flex items-end gap-[2px] h-24 w-full mt-4 px-1"
      role="img"
      aria-label="Audio visualizer"
    >
      {Array.from({ length: BAR_COUNT }).map((_, i) => (
        <div
          key={i}
          ref={(el) => { barRefs.current[i] = el; }}
          className="flex-1 rounded-t-[2px] visualizer-bar"
          style={{
            height: '8%',
            background:
              'linear-gradient(to top, color-mix(in srgb, var(--theme-primary) 35%, transparent), var(--theme-primary))',
            boxShadow: '0 0 6px color-mix(in srgb, var(--theme-primary) 40%, transparent)',
          }}
        />
      ))}
    </div>
  );
};

AudioVisualizer.propTypes = {
  trackId: PropTypes.string,
  isPlaying: PropTypes.bool,
  progressMs: PropTypes.number,
};

export default AudioVisualizer;
