import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import { Clock, Thermometer, Mail, Calendar, Music } from 'lucide-react';
import { API_BASE_URL } from '../config';
import { formatLocalTime } from '../utils/timeUtils';

const SituationalAwareness = () => {
  const [saData, setSaData] = useState([]);

  useEffect(() => {
    const fetchSA = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/situational-awareness`);
        if (response.ok) {
          const data = await response.json();
          setSaData(data || []);
        }
      } catch (error) {
        console.error('Failed to fetch SA:', error);
      }
    };

    fetchSA();
    const saTimer = setInterval(fetchSA, 60000); // Poll every 60s
    return () => clearInterval(saTimer);
  }, []);

  const getIcon = (mode) => {
    switch (mode) {
      case 'time': return <Clock className="w-6 h-6 text-primary drop-shadow-lg" />;
      case 'weather': return <Thermometer className="w-6 h-6 text-error drop-shadow-lg" />;
      case 'email': return <Mail className="w-6 h-6 text-primary drop-shadow-lg" />;
      case 'event': return <Calendar className="w-6 h-6 text-success drop-shadow-lg" />;
      case 'music': return <Music className="w-6 h-6 text-secondary drop-shadow-lg" />;
      default: return <Thermometer className="w-6 h-6 text-error drop-shadow-lg" />;
    }
  };

  return (
    <div className="glass rounded-2xl p-6 border border-primary/30 bg-card/20">
      <h2 className="text-xl font-bold text-primary mb-4 drop-shadow-lg">Situational Awareness</h2>

      <div className="space-y-4">
        {saData.length > 0 ? (
          saData.slice(0, 4).map((card, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1 }}
              className="flex items-center space-x-3"
            >
              {getIcon(card.mode)}
              <div>
                <p className="text-sm text-text-tertiary capitalize">{card.mode || 'Status'}</p>
                <p className="text-lg font-mono text-text-primary">{card.mode === 'time' ? new Date(card.content).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }) : (card.content || 'No data')}</p>
                <p className="text-xs text-text-tertiary">Priority: {card.priority || 4}</p>
              </div>
            </motion.div>
          ))
        ) : (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center space-x-3"
          >
            <Thermometer className="w-6 h-6 text-error drop-shadow-lg" />
            <div>
              <p className="text-sm text-text-tertiary">Loading</p>
              <p className="text-lg font-mono text-text-primary">Fetching data...</p>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
};

export default SituationalAwareness;