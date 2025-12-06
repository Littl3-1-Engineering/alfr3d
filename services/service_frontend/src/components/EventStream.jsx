import { motion, AnimatePresence } from 'framer-motion';
import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';
import { formatLocalTime } from '../utils/timeUtils';

const EventStream = () => {
  const [displayedEvents, setDisplayedEvents] = useState([]);

  useEffect(() => {
    const fetchEvents = async () => {
      try {
        const response = await fetch(API_BASE_URL + '/api/events');
        const events = await response.json();
        // Reverse to show newest first, limit to 4
        const latestEvents = events.reverse().slice(0, 4);
        setDisplayedEvents(latestEvents);
      } catch (error) {
        console.error('Error fetching events:', error);
      }
    };

    fetchEvents();
    const interval = setInterval(fetchEvents, 5000); // Update every 5 seconds
    return () => clearInterval(interval);
  }, []);

  const getIcon = (type) => {
    switch (type) {
      case 'warning': return <div className="w-3 h-3 border-2 border-warning" />;
      case 'success': return <div className="w-3 h-3 border-2 border-fui-accent bg-fui-accent" />;
      default: return <div className="w-3 h-3 border-2 border-fui-text" />;
    }
  };

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
            {getIcon(event.type)}
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
