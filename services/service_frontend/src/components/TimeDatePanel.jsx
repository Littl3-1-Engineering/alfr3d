import { motion } from 'framer-motion';
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
          TIME & DATE
        </h3>
      </div>

      {/* Content Area */}
      <div className="p-4 relative pt-8">
        <div className="text-center">
          <div className="text-3xl font-mono text-fui-accent mb-2">
            {formatTime(currentTime)}
          </div>
          <div className="text-sm font-mono text-fui-text uppercase">
            {formatDate(currentTime)}
          </div>
        </div>
      </div>
    </motion.div>
  );
};

export default TimeDatePanel;
