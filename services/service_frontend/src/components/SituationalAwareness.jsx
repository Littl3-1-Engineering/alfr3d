import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import { Clock, Thermometer, Mail, Calendar, Music } from 'lucide-react';
import { API_BASE_URL } from '../config';

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
      case 'time': return <Clock className="text-fui-accent" />;
      case 'weather': return <Thermometer className="text-error" />;
      case 'email': return <Mail className="text-fui-accent" />;
      case 'event': return <Calendar className="text-fui-accent" />;
      case 'music': return <Music className="text-fui-text" />;
      default: return <Thermometer className="text-error" />;
    }
  };

  return (
    <div className="space-y-4">
      {saData.length > 0 ? (
        saData.slice(0, 4).map((card, index) => (
          <motion.div
            key={index}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
            className="flex items-center space-x-3 p-2 border border-fui-border/30 hover:border-fui-accent/50 transition-colors duration-200"
          >
            <div className="w-6 h-6 flex items-center justify-center flex-shrink-0">{getIcon(card.mode)}</div>
            <div>
              <p className="text-sm text-fui-text/60 font-mono uppercase">[{card.mode || 'STATUS'}]</p>
              <p className="text-lg font-mono text-fui-text">{card.mode === 'time' ? new Date(card.content).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }) : (card.content || 'NO DATA')}</p>
              <p className="text-xs text-fui-text/60 font-mono">PRIO: {card.priority || 4}</p>
            </div>
          </motion.div>
        ))
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
           className="flex items-center space-x-3 p-2 border border-fui-border/30"
        >
          <div className="w-6 h-6 flex items-center justify-center flex-shrink-0"><Thermometer className="text-error" /></div>
          <div>
            <p className="text-sm text-fui-text/60 font-mono">[ LOADING ]</p>
            <p className="text-lg font-mono text-fui-text">FETCHING DATA...</p>
          </div>
        </motion.div>
      )}
    </div>
  );
};

export default SituationalAwareness;
