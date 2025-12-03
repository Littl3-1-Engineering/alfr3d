import PropTypes from 'prop-types';
import { useMemo } from 'react';
import { motion } from 'framer-motion';
import Modal from 'react-modal';
import { Monitor, X } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

Modal.setAppElement('#root');

Modal.setAppElement('#root');

const DeviceHistoryModal = ({ isOpen, onClose, device, history }) => {

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

        {/* Activity Graph Section */}
        <div>
          <h3 className="text-xl font-bold text-primary mb-4">
            Activity Graph ({dailyActivity.length} days)
          </h3>
          {dailyActivity.length > 0 ? (
            <div className="h-96">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={dailyActivity.map(day => ({ date: formatDate(day.date), count: day.count }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis dataKey="date" stroke="var(--color-text-secondary)" />
                  <YAxis stroke="var(--color-text-secondary)" />
                  <Tooltip
                    contentStyle={{ backgroundColor: 'var(--color-card)', border: '1px solid var(--color-primary)', borderRadius: '8px' }}
                    labelStyle={{ color: 'var(--color-text-primary)' }}
                  />
                  <Line type="monotone" dataKey="count" stroke="var(--color-primary)" strokeWidth={2} dot={{ fill: 'var(--color-primary)' }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="text-center text-text-tertiary py-8">
              No activity found for this device in the last 6 months
            </div>
          )}
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
