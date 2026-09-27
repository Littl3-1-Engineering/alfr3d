import { useEffect, useState } from 'react';
import { API_BASE_URL } from '../config';
import socket from './socket';

// Fallback polling only while the socket isn't connected -- the "update_status" WS channel
// (service-api re-broadcasting the updater container's status file) is the primary source once
// it's up.
const POLL_INTERVAL_MS = 5000;

export const useUpdateStatus = () => {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    let cancelled = false;

    const fetchStatus = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/system/update/status`);
        if (res.ok && !cancelled) setStatus(await res.json());
      } catch (e) { console.error('update status fetch failed', e); }
    };

    fetchStatus();

    const handleUpdateStatus = (data) => {
      if (!cancelled) setStatus(data);
    };
    const unsubscribe = socket.on('update_status', handleUpdateStatus);

    const interval = setInterval(() => {
      if (!socket.isConnected) fetchStatus();
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      unsubscribe();
      clearInterval(interval);
    };
  }, []);

  return status;
};
