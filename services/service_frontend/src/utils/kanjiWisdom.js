// The daily katakana quote overlay (todo/todo_kanji_wisdom_quotes.md). The backend owns the list
// and picks one per household-local day (GET /api/kanji/today); this file only holds the
// browser-side preference and the decode-effect maths.
export const KANJI_WISDOM_STORAGE_KEY = 'alfr3d-kanji-wisdom';
export const defaultKanjiWisdom = true;

// Re-scramble cadence, to draw the eye -- same as the Deck.
export const KANJI_REPLAY_MS = 30_000;
export const KANJI_SCRAMBLE_STEPS = 16;
export const KANJI_SCRAMBLE_STEP_MS = 55;

// Glyphs the decode effect flickers through before a character resolves. Katakana, so
// the noise reads as "other writing" rather than boxes or symbols.
const SCRAMBLE_POOL = Array.from('アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワン');

// One frame of the left-to-right (top-to-bottom, in the vertical column) decode: characters
// before the reveal point are the real text, the rest are random pool glyphs. `step` runs from
// 0 (all noise) to steps - 1 (almost resolved); the caller shows the real text afterwards.
export const scrambleFrame = (text, step, steps = KANJI_SCRAMBLE_STEPS, random = Math.random) => {
  const chars = Array.from(text);
  const revealed = Math.floor((chars.length * step) / steps);
  return chars
    .map((c, i) => (i < revealed ? c : SCRAMBLE_POOL[Math.floor(random() * SCRAMBLE_POOL.length)]))
    .join('');
};
