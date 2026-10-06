import { useEffect, useState } from 'react';
import { useReducedMotion } from 'framer-motion';
import { useKanjiToday } from '../hooks/useApi';
import { useUiPrefs } from '../utils/useUiPrefs';
import {
  KANJI_REPLAY_MS,
  KANJI_SCRAMBLE_STEPS,
  KANJI_SCRAMBLE_STEP_MS,
  scrambleFrame,
} from '../utils/kanjiWisdom';

const TEXT_SHADOW = '0 0 6px rgba(0, 0, 0, 0.85)';

// Today's kanji quote as an ambient layer: the kanji run vertically (tategaki) up the
// bottom-left edge and the reading + meaning sit in two left-aligned rows along the bottom.
// It re-decodes every 30 s to draw the eye. Purely decorative and non-interactive
// (pointer-events none), so the translation is always visible rather than behind a tap; the
// same text is exposed to assistive tech on the wrapper. Reduced motion shows plain text and
// never re-scrambles. Renders nothing when switched off, while loading, or if the backend has
// no quote to give.
const KanjiWisdom = () => {
  const { kanjiWisdom } = useUiPrefs();
  const reducedMotion = useReducedMotion();
  const { data } = useKanjiToday(kanjiWisdom);
  const kanji = data?.kanji;
  const [scrambled, setScrambled] = useState(null);

  useEffect(() => {
    if (!kanji || reducedMotion) return undefined;
    let cancelled = false;
    let timer;
    const play = (step) => {
      if (cancelled) return;
      if (step >= KANJI_SCRAMBLE_STEPS) {
        setScrambled(null);
        timer = setTimeout(() => play(0), KANJI_REPLAY_MS);
        return;
      }
      setScrambled(scrambleFrame(kanji, step));
      timer = setTimeout(() => play(step + 1), KANJI_SCRAMBLE_STEP_MS);
    };
    play(0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [kanji, reducedMotion]);

  if (!kanjiWisdom || !kanji) return null;

  const shown = reducedMotion || scrambled === null ? kanji : scrambled;
  const label = `${kanji}, ${data.reading}: ${data.meaning}`;

  return (
    <div
      data-testid="kanji-wisdom"
      role="img"
      aria-label={label}
      className="pointer-events-none fixed inset-0 z-[15] select-none"
    >
      <div
        aria-hidden="true"
        data-testid="kanji-wisdom-kanji"
        className="absolute left-2 bottom-20 text-lg leading-snug"
        style={{
          writingMode: 'vertical-rl',
          textOrientation: 'upright',
          color: 'var(--theme-primary)',
          opacity: 0.85,
          textShadow: TEXT_SHADOW,
        }}
      >
        {shown}
      </div>
      <div
        aria-hidden="true"
        className="absolute left-4 bottom-3 max-w-[calc(100vw-2rem)] text-xs leading-relaxed"
        style={{ color: 'var(--theme-primary)', opacity: 0.75, textShadow: TEXT_SHADOW }}
      >
        <div className="font-mono">{data.reading}</div>
        <div className="font-tech">{data.meaning}</div>
      </div>
    </div>
  );
};

export default KanjiWisdom;
