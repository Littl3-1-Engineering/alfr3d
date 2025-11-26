import PropTypes from 'prop-types';
import { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import Modal from 'react-modal';
import { Monitor, X } from 'lucide-react';

Modal.setAppElement('#root');

Modal.setAppElement('#root');

const DeviceHistoryModal = ({ isOpen, onClose, device, history }) => {
  const [expandedDays, setExpandedDays] = useState(new Set());

  // Process history data into daily groups, limited to 6 months
  const dailyActivity = useMemo(() => {
    if (!history || history.length === 0) return [];

    const sixMonthsAgo = new Date();
    sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);

    const dailyGroups = {};

    history
      .filter(entry => new Date(entry.timestamp) >= sixMonthsAgo)
      .forEach(entry => {
        const date = entry.timestamp.split('T')[0]; // YYYY-MM-DD
        if (!dailyGroups[date]) {
          dailyGroups[date] = {
            date,
            count: 0,
            entries: [],
            states: new Set()
          };
        }
        dailyGroups[date].count++;
        dailyGroups[date].entries.push(entry);
        if (entry.state) {
          dailyGroups[date].states.add(entry.state);
        }
      });

    // Sort by date (oldest first for timeline)
    return Object.values(dailyGroups).sort((a, b) => a.date.localeCompare(b.date));
  }, [history]);

  const toggleDayExpansion = (date) => {
    const newExpanded = new Set(expandedDays);
    if (newExpanded.has(date)) {
      newExpanded.delete(date);
    } else {
      newExpanded.add(date);
    }
    setExpandedDays(newExpanded);
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (date.toDateString() === today.toDateString()) {
      return 'Today';
    } else if (date.toDateString() === yesterday.toDateString()) {
      return 'Yesterday';
    } else {
      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: date.getFullYear() !== today.getFullYear() ? 'numeric' : undefined
      });
    }
  };

  const getActivityLevel = (count) => {
    if (count >= 10) return 'high';
    if (count >= 5) return 'medium';
    return 'low';
  };
  return (
    <Modal
      isOpen={isOpen}
      onRequestClose={onClose}
      className="modal-content"
      overlayClassName="modal-overlay"
      contentLabel="Device History"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.9 }}
        className="glass rounded-2xl p-6 border border-primary/30 bg-card/20 max-w-4xl w-full max-h-[90vh] overflow-hidden"
      >
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center space-x-3">
            <Monitor className="w-8 h-8 text-primary" />
            <div>
              <h2 className="text-2xl font-bold text-primary">{device?.name}</h2>
              <p className="text-sm text-primary uppercase">{device?.type}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-text-tertiary hover:text-primary transition-colors text-2xl"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Device Details */}
        <div className="mb-6 grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <div className="text-sm text-text-secondary">
              <span className="text-primary font-medium">IP:</span> {device?.ip}
            </div>
            <div className="text-sm text-text-secondary">
              <span className="text-primary font-medium">MAC:</span> {device?.mac}
            </div>
            <div className="text-sm text-text-secondary">
              <span className="text-primary font-medium">State:</span> {device?.state}
            </div>
          </div>
          <div className="space-y-2">
            <div className="text-sm text-text-secondary">
              <span className="text-primary font-medium">User:</span> {device?.user || 'None'}
            </div>
            <div className="text-sm text-text-secondary">
              <span className="text-primary font-medium">Last Online:</span> {device?.last_online}
            </div>
          </div>
        </div>

        {/* Timeline Section */}
        <div>
          <h3 className="text-xl font-bold text-primary mb-4">
            Activity Timeline ({dailyActivity.length} days)
          </h3>
          <div className="max-h-96 overflow-y-auto">
            {dailyActivity.length > 0 ? (
              <div className="timeline-container">
                {dailyActivity.map((day, index) => (
                  <motion.div
                    key={day.date}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.05 }}
                    className="timeline-item"
                  >
                    {/* Timeline connector */}
                    <div className="timeline-connector">
                      <div className="timeline-dot"></div>
                      {index < dailyActivity.length - 1 && <div className="timeline-line"></div>}
                    </div>

                    {/* Timeline content */}
                    <div className="timeline-content">
                      <div
                        className="timeline-header cursor-pointer"
                        onClick={() => toggleDayExpansion(day.date)}
                      >
                        <div className="timeline-date">{formatDate(day.date)}</div>
                        <div className="timeline-meta">
                          <span className={`activity-badge activity-${getActivityLevel(day.count)}`}>
                            {day.count} {day.count === 1 ? 'activity' : 'activities'}
                          </span>
                          <div className="state-indicators">
                            {Array.from(day.states).map(state => (
                              <span key={state} className={`state-badge state-${state?.toLowerCase()}`}>
                                {state}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>

                      {/* Expandable details */}
                      {expandedDays.has(day.date) && (
                        <motion.div
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                          className="timeline-details"
                        >
                          <div className="space-y-2">
                            {day.entries.map((entry, entryIndex) => (
                              <div key={entryIndex} className="history-entry">
                                <div className="flex justify-between text-sm mb-1">
                                  <span className="text-primary font-medium">
                                     {new Date(entry.timestamp).toLocaleTimeString('en-US', {
                                       hour: '2-digit',
                                       minute: '2-digit',
                                       hour12: false
                                     })}
                                  </span>
                                  <span className="text-text-tertiary">{entry.state}</span>
                                </div>
                                <div className="text-xs text-text-secondary space-y-1">
                                  {entry.name !== device?.name && (
                                    <div>Name: <span className="text-text-inverse">{entry.name}</span></div>
                                  )}
                                  {entry.ip !== device?.ip && (
                                    <div>IP: <span className="text-text-inverse">{entry.ip}</span></div>
                                  )}
                                  {entry.mac !== device?.mac && (
                                    <div>MAC: <span className="text-text-inverse">{entry.mac}</span></div>
                                  )}
                                  {entry.user && (
                                    <div>User: <span className="text-text-inverse">{entry.user}</span></div>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        </motion.div>
                      )}
                    </div>
                  </motion.div>
                ))}
              </div>
            ) : (
              <div className="text-center text-text-tertiary py-8">
                No activity found for this device in the last 6 months
              </div>
            )}
          </div>
        </div>
      </motion.div>
    </Modal>
  );
};

DeviceHistoryModal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  device: PropTypes.object,
  history: PropTypes.array,
};

export default DeviceHistoryModal;