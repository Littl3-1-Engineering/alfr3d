// Sort helpers for roster/registry lists.

const _timeOf = (value) => {
  if (!value) return NaN;
  return new Date(value).getTime();
};

// Sort items online-first, then offline sorted by most-recently online.
// Items with no known last-online time sort last. Never mutates the input.
export const sortByOnlineState = (
  items,
  isOnline = (item) => item.state === 'online',
  lastOnline = (item) => item.last_online
) =>
  [...items].sort((a, b) => {
    const aOnline = isOnline(a) ? 1 : 0;
    const bOnline = isOnline(b) ? 1 : 0;
    if (aOnline !== bOnline) return bOnline - aOnline;

    const aTime = _timeOf(lastOnline(a));
    const bTime = _timeOf(lastOnline(b));
    if (Number.isNaN(aTime) && Number.isNaN(bTime)) return 0;
    if (Number.isNaN(aTime)) return 1;
    if (Number.isNaN(bTime)) return -1;
    return bTime - aTime;
  });
