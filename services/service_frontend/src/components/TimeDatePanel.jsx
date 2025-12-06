import { useState, useEffect } from 'react';

const TimeDatePanel = () => {
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  const formatTime = (date) => {
    return date.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  const formatDate = (date) => {
    return date.toLocaleDateString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  };

  return (
    <div className="p-4 relative">
      <div className="text-center">
        <div className="text-3xl font-mono text-fui-accent mb-2">
          {formatTime(currentTime)}
        </div>
        <div className="text-sm font-mono text-fui-text uppercase">
          {formatDate(currentTime)}
        </div>
      </div>
    </div>
  );
};

export default TimeDatePanel;
