import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';

const CalendarPanel = () => {
  const [events, setEvents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(false);
  const [currentDate] = useState(new Date());

  useEffect(() => {
    const fetchEvents = async () => {
      try {
        setIsLoading(true);
        setError(false);
        const response = await fetch(`${API_BASE_URL}/api/calendar/events`);
        if (response.ok) {
          const data = await response.json();
          setEvents(data);
        } else {
          setError(true);
        }
      } catch (error) {
        console.error('Failed to fetch calendar events:', error);
        setError(true);
      } finally {
        setIsLoading(false);
      }
    };

    fetchEvents();
    const eventTimer = setInterval(fetchEvents, 300000); // Update every 5 minutes
    return () => clearInterval(eventTimer);
  }, []);

  const getDaysInMonth = (date) => {
    const year = date.getFullYear();
    const month = date.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const daysInMonth = lastDay.getDate();
    const startingDayOfWeek = firstDay.getDay();

    const days = [];

    // Add empty cells for days before the first day of the month
    for (let i = 0; i < startingDayOfWeek; i++) {
      days.push(null);
    }

    // Add days of the month
    for (let day = 1; day <= daysInMonth; day++) {
      days.push(day);
    }

    return days;
  };

  const formatTime = (isoString) => {
    if (!isoString) return '';
    const date = new Date(isoString);
    return date.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const today = new Date();
  const isToday = (day) => {
    return day === today.getDate() &&
           currentDate.getMonth() === today.getMonth() &&
           currentDate.getFullYear() === today.getFullYear();
  };

  const days = getDaysInMonth(currentDate);
  const monthName = currentDate.toLocaleDateString('en-US', { month: 'long' });
  const year = currentDate.getFullYear();

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6 }}
      className="relative bg-fui-panel border border-fui-border rounded-none"
    >
      {/* Corner Markers */}
      <div className="absolute -top-px -left-px w-3 h-3 border-t-2 border-l-2 border-fui-accent z-10" />
      <div className="absolute -top-px -right-px w-3 h-3 border-t-2 border-r-2 border-fui-accent z-10" />
      <div className="absolute -bottom-px -left-px w-3 h-3 border-b-2 border-l-2 border-fui-accent z-10" />
      <div className="absolute -bottom-px -right-px w-3 h-3 border-b-2 border-r-2 border-fui-accent z-10" />

      {/* Custom Folder Tab Header */}
      <div className="absolute top-0 right-0 border-l-4 border-fui-accent bg-black/60 px-2 py-1 z-20">
        <h3 className="font-tech text-lg text-white uppercase">
          CALENDAR
        </h3>
      </div>

      {/* Content Area */}
      <div className="p-4 relative pt-8">
        {/* Month Header */}
        <div className="text-center mb-3">
          <h4 className="text-sm font-mono text-fui-accent uppercase">
            {monthName} {year}
          </h4>
        </div>

        {/* Calendar Grid */}
        <div className="grid grid-cols-7 gap-1 mb-4 text-xs">
          {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map(day => (
            <div key={day} className="text-center text-fui-text/60 font-mono uppercase">
              {day}
            </div>
          ))}
          {days.map((day, index) => (
            <div
              key={index}
              className={`text-center text-xs font-mono p-1 ${
                day ? (isToday(day) ? 'text-fui-accent bg-fui-accent/20' : 'text-fui-text') : ''
              }`}
            >
              {day}
            </div>
          ))}
        </div>

        {/* Today's Events */}
        <div>
          <h5 className="text-xs font-mono text-fui-text/60 uppercase mb-2">TODAY&apos;S EVENTS</h5>
          {isLoading ? (
            <p className="text-fui-accent font-mono uppercase text-xs">LOADING...</p>
          ) : error ? (
            <p className="text-red-400 font-mono uppercase text-xs">ERROR LOADING EVENTS</p>
          ) : events.length === 0 ? (
            <p className="text-fui-text/60 font-mono text-xs">NO EVENTS TODAY</p>
          ) : (
             <div className="space-y-1">
              {events.map((event, index) => (
                <div key={index} className="text-xs">
                  <div className="flex justify-between">
                    <span className="text-fui-text font-mono truncate">{event.title}</span>
                    <span className="text-fui-text/60 font-mono ml-1">
                      {formatTime(event.start_time)}
                    </span>
                  </div>
                  {event.address && (
                    <div className="text-fui-text/60 font-mono text-xs truncate">
                      {event.address}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
};

export default CalendarPanel;
