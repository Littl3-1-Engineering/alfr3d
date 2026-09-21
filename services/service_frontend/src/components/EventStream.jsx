import { motion, AnimatePresence } from 'framer-motion';
import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';
import { formatLocalTime } from '../utils/timeUtils';
import socket from '../utils/socket';
import HudRing from './HudRing';

const EventStream = () => {
  const [displayedEvents, setDisplayedEvents] = useState([]);

  useEffect(() => {
    const fetchEvents = async () => {
      try {
        const response = await fetch(API_BASE_URL + '/api/events');
        if (response.ok) {
          const events = await response.json();
          const latestEvents = events.reverse().slice(0, 4);
          setDisplayedEvents(latestEvents);
        }
      } catch (error) {
        console.error('Error fetching events:', error);
      }
    };

    fetchEvents();

    socket.on('events', (events) => {
      const latestEvents = events.reverse().slice(0, 4);
      setDisplayedEvents(latestEvents);
    });

    return () => {
      socket.off('events');
    };
  }, []);

  // Shape tells the event kinds apart; colour is left to carry severity alone. These are
  // deliberately the identity shapes (see todo/todo_cyber_hud_buttons_frontend.md) —
  // compass/splitArc/gear are reserved for acquire/sync/compute and would misread here,
  // since every line in a log is something that already happened.
  //
  // The real event types come from the services: success, info, warning and audio
  // (service_device/app.py, service_user/app.py, service_daemon/utils/now_playing_monitor.py).
  const RING = {
    success: { shape: 'reticle', tone: 'cyan' },
    warning: { shape: 'scanner', tone: 'amber' },
    audio: { shape: 'node', tone: 'cyan' },
    info: { shape: 'sensor', tone: 'cyan' },
  };
  const ringFor = (type) => RING[type] || { shape: 'iris', tone: 'cyan' };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6 }}
      className="relative bg-fui-panel rounded-none"
    >
      {/* Content Area */}
      <div className="p-2 relative pt-4">
        <div className="space-y-3 h-full pb-4">
          <AnimatePresence>
        {displayedEvents.map((event, index) => (
          <motion.div
            key={event.id}
            initial={{ opacity: 0, y: -20, scale: 0.95 }}
            animate={{ opacity: 1 - (index * 0.2), y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ duration: 0.3 }}
            className="flex items-start space-x-3 p-3 border border-fui-border/30 hover:border-fui-accent/50 transition-colors duration-200"
          >
            {/* Only the newest event bounces. Older rows are keyed by event.id and simply
                re-render as idle when something newer arrives, so the settle happens once,
                on arrival, and never replays. */}
            <HudRing
              shape={ringFor(event.type).shape}
              tone={ringFor(event.type).tone}
              state={index === 0 ? 'resolve' : 'idle'}
              size={16}
              className="mt-0.5 shrink-0"
            />
            <div className="flex-1">
              <p className="text-sm text-fui-text font-mono">{event.message}</p>
               <p className="text-xs text-fui-text/60 mt-1 font-mono">[{formatLocalTime(event.time)}]</p>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
};

export default EventStream;
