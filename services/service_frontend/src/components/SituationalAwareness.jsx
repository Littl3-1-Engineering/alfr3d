import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Clock, Thermometer, Mail, Calendar, Music, Smile, PhoneCall, CloudRain, Car } from 'lucide-react';
import { API_BASE_URL } from '../config';
import { formatTimeWithTimezone } from '../utils/timeUtils';
import socket from '../utils/socket';

// Matches MAX_DISPLAYS in service_daemon/alfr3ddaemon.py (len(DISPLAY_RULES) = 9
// registered card types). Keep in sync -- a lower cap here silently drops cards
// the backend intentionally raised its own cap to stop dropping.
const MAX_DISPLAY_CARDS = 9;

const SituationalAwareness = ({ timezone = null }) => {
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

    socket.on('situational_awareness', (data) => {
      setSaData(data || []);
    });

    return () => {
      socket.off('situational_awareness');
    };
  }, []);

  const getIcon = (mode) => {
    switch (mode) {
      case 'time': return <Clock className="text-fui-accent" />;
      case 'weather': return <Thermometer className="text-error" />;
      case 'email': return <Mail className="text-fui-accent" />;
      case 'event': return <Calendar className="text-fui-accent" />;
      case 'music': return <Music className="text-fui-text" />;
      // Ambient context, not an actionable alert -- cyan like the other status cards.
      case 'mood': return <Smile className="text-fui-accent" />;
      // Time-boxed and actionable ("find a quiet spot") -- magenta alert treatment.
      case 'focus_needed': return <PhoneCall className="text-fui-magenta" />;
      // Forward-looking and actionable ("bring an umbrella"), unlike the passive
      // weather readout above -- magenta, and a distinct icon from Thermometer.
      case 'weather_advisory': return <CloudRain className="text-fui-magenta" />;
      // Leave-by guidance is as time-boxed/actionable as focus_needed -- same treatment.
      case 'travel': return <Car className="text-fui-magenta" />;
      default: return <Thermometer className="text-error" />;
    }
  };

  return (
    <div className="space-y-4">
      {saData.length > 0 ? (
        saData.slice(0, MAX_DISPLAY_CARDS).map((card, index) => (
          <motion.div
            key={index}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
            className="flex items-center space-x-3 p-2 border border-fui-border/30 hover:border-fui-accent/50 transition-colors duration-200"
          >
            <div className="w-6 h-6 flex items-center justify-center flex-shrink-0">{getIcon(card.mode)}</div>
            <div className="min-w-0 flex-1">
              <p className="text-sm text-fui-text/60 font-mono uppercase">[{card.mode || 'STATUS'}]</p>
              <p className="text-lg font-mono text-fui-text break-words">{card.mode === 'time' ? formatTimeWithTimezone(card.content, timezone) : (card.content || 'NO DATA')}</p>
              {card.mode === 'music' && card.playlist_name && (
                <a
                  href={card.playlist_url || undefined}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center space-x-2 mt-1 text-xs font-mono text-fui-accent hover:underline min-w-0"
                >
                  {card.playlist_image && (
                    <img src={card.playlist_image} alt="" className="w-6 h-6 object-cover flex-shrink-0" />
                  )}
                  <span className="break-words min-w-0">▶ {card.playlist_name}</span>
                </a>
              )}
              {card.mode === 'music' && card.track_title && (
                <p className="mt-1 text-xs font-mono text-fui-text/80 break-words">
                  ♪ {card.track_title}{card.track_artist ? ` — ${card.track_artist}` : ''}
                </p>
              )}
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

SituationalAwareness.propTypes = {
  timezone: PropTypes.string,
};

export default SituationalAwareness;
