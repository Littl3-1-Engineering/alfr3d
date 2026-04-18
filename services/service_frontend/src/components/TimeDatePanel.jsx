import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { getCurrentTimeWithTimezone, formatDateWithTimezone } from '../utils/timeUtils';

const TimeDatePanel = ({ timezone = null }) => {
  const [currentTime, setCurrentTime] = useState(() => getCurrentTimeWithTimezone(timezone));

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(getCurrentTimeWithTimezone(timezone));
    }, 1000);

    return () => clearInterval(timer);
  }, [timezone]);

  const formatTime = (date) => {
    return date.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  return (
    <div className="p-4 relative">
      <div className="text-center">
        <div className="text-3xl font-mono text-fui-accent mb-2">
          {formatTime(currentTime)}
        </div>
        <div className="text-sm font-mono text-fui-text uppercase">
          {formatDateWithTimezone(timezone)}
        </div>
      </div>
    </div>
  );
};

TimeDatePanel.propTypes = {
  timezone: PropTypes.number,
};

export default TimeDatePanel;
