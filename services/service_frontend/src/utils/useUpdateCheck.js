import { useEffect, useState } from 'react';
import { API_BASE_URL } from '../config';

// Releases don't ship more than a few times a week -- polling more often than this just adds
// load for no benefit, and the backend caches the GitHub response for a similar window anyway.
const POLL_INTERVAL_MS = 6 * 60 * 60 * 1000;

export const useUpdateCheck = () => {
  const [updateInfo, setUpdateInfo] = useState(null);

  useEffect(() => {
    let cancelled = false;

    const fetchUpdateCheck = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/system/update-check`);
        if (res.ok && !cancelled) setUpdateInfo(await res.json());
      } catch (e) { console.error('update-check fetch failed', e); }
    };

    fetchUpdateCheck();
    const interval = setInterval(fetchUpdateCheck, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return updateInfo;
};
