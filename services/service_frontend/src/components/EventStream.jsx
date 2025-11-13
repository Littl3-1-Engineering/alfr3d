import { motion, AnimatePresence } from 'framer-motion';
import { useState, useEffect } from 'react';
import { Clock, AlertTriangle, CheckCircle } from 'lucide-react';
import { API_BASE_URL } from '../config';

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
      case 'warning': return <AlertTriangle className="w-4 h-4 text-yellow-400" />;
      case 'success': return <CheckCircle className="w-4 h-4 text-green-400" />;
      default: return <Clock className="w-4 h-4 text-cyan-400" />;
    }
  };

  return (
    <div className="glass rounded-2xl p-6 h-96 border border-cyan-500/30 bg-slate-800/20">
      <h2 className="text-xl font-bold text-cyan-400 mb-4 drop-shadow-lg">Event Stream</h2>
      <div className="space-y-3 h-full pb-4">
        <AnimatePresence>
          {displayedEvents.map((event, index) => (
            <motion.div
              key={event.id}
              initial={{ opacity: 0, y: -20, scale: 0.95 }}
              animate={{ opacity: 1 - (index * 0.2), y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 20, scale: 0.95 }}
              transition={{ duration: 0.3 }}
              className="flex items-start space-x-3 p-3 rounded-lg bg-slate-800/30 w-full"
            >
              {getIcon(event.type)}
              <div className="flex-1">
                <p className="text-sm text-gray-300">{event.message}</p>
                <p className="text-xs text-gray-500 mt-1">{event.time}</p>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
};

export default EventStream;