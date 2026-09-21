// src/hooks/useSettleOnChange.js
//
// Answers "which of these things just changed?" so a HudRing can play its bounce-settle at
// the moment real state flips, rather than on every render or every socket push.
//
// The distinction matters: the WebSocket re-broadcasts the whole users/devices/containers
// list on any change, so re-rendering is not evidence that a given entity changed. This
// compares values, keyed per entity, and reports only the keys whose value actually moved.
//
// The first run never reports anything — a page load is not a state change, and the whole
// Core lighting up on arrival would make the signal meaningless.

import { useEffect, useRef, useState } from 'react';

const EMPTY = new Set();

// Long enough for the slowest resolve in the set (Gear Dial, 1.5s) to finish before the
// ring drops back to its resting state.
const DEFAULT_HOLD_MS = 1600;

// Above this many at once, it is a bulk load rather than a set of real events.
const MAX_SIMULTANEOUS = 3;

/**
 * @param {Object<string, string|number>} signatures - entity key -> a value that changes
 *   when that entity's state does. Memoize it at the call site.
 * @param {number} [holdMs] - how long a key stays reported as settling.
 * @returns {Set<string>} the keys currently settling.
 */
export const useSettleOnChange = (signatures, holdMs = DEFAULT_HOLD_MS) => {
  const previous = useRef(null);
  const [settling, setSettling] = useState(EMPTY);

  useEffect(() => {
    const before = previous.current;
    previous.current = signatures;

    // First run: nothing to compare against, and arrival is not a change.
    if (before === null) return undefined;

    // A key appearing counts too, not just one whose value moved. The users list is
    // filtered to online members upstream, so somebody coming home shows up as a brand new
    // key rather than a changed one -- and that arrival is exactly the event worth marking.
    const changed = Object.keys(signatures).filter(
      (key) => !(key in before) || before[key] !== signatures[key],
    );
    if (changed.length === 0) return undefined;

    // A whole list landing at once is a bulk load (first socket push, a reconnect, a
    // refetch), not a series of events. Bouncing every ring together would be noise and
    // would break the "at most one ring animating per region" rule, so report nothing.
    if (changed.length > MAX_SIMULTANEOUS) return undefined;

    setSettling((current) => {
      const next = new Set(current);
      changed.forEach((key) => next.add(key));
      return next;
    });

    const timer = setTimeout(() => {
      setSettling((current) => {
        const next = new Set(current);
        changed.forEach((key) => next.delete(key));
        return next.size === 0 ? EMPTY : next;
      });
    }, holdMs);

    return () => clearTimeout(timer);
  }, [signatures, holdMs]);

  return settling;
};

export default useSettleOnChange;
