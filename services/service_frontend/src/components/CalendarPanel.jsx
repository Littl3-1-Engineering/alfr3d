import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';
import socket from '../utils/socket';
import { formatTimeWithTimezone } from '../utils/timeUtils';

const CalendarPanel = ({ initialEvents = null, initialTimezone = null, pollInterval = 300000 }) => {
  const [events, setEvents] = useState(initialEvents || []);
  const [isLoading, setIsLoading] = useState(!initialEvents);
  const [error, setError] = useState(false);
  const [currentDate] = useState(new Date());

  const fetchEvents = async () => {
    try {
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
    }
  };

  useEffect(() => {
    if (!initialEvents) {
      fetchEvents().finally(() => setIsLoading(false));
    }
    const eventTimer = setInterval(fetchEvents, pollInterval);

    const handleEventsUpdate = (data) => {
      setEvents(data);
      setIsLoading(false);
    };

    socket.on('events', handleEventsUpdate);

    return () => {
      clearInterval(eventTimer);
      socket.off('events', handleEventsUpdate);
    };
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
    return formatTimeWithTimezone(isoString, initialTimezone) || '';
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
    <div className="p-4 relative">
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
  );
};

export default CalendarPanel;
