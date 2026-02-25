import PropTypes from 'prop-types';
import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import Modal from 'react-modal';
import { Monitor, X, Edit, Save, RotateCcw } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

Modal.setAppElement('#root');

const DeviceHistoryModal = ({ isOpen, onClose, device, history, users, onSave }) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editedDevice, setEditedDevice] = useState(null);

  const handleEdit = () => {
    setIsEditing(true);
    setEditedDevice({ ...device });
  };

  const handleCancel = () => {
    setIsEditing(false);
    setEditedDevice(null);
  };

  const handleSave = async () => {
    if (onSave && editedDevice) {
      const success = await onSave(editedDevice);
      if (success) {
        setIsEditing(false);
        setEditedDevice(null);
      }
    }
  };

  const handleInputChange = (field, value) => {
    setEditedDevice(prev => ({ ...prev, [field]: value }));
  };

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
              {isEditing ? (
                <div className="space-y-1">
                  <input
                    value={editedDevice?.name || ''}
                    onChange={(e) => handleInputChange('name', e.target.value)}
                    className="text-2xl font-bold text-primary bg-transparent border-b border-primary/50 focus:border-primary outline-none"
                  />
                  <select
                    value={editedDevice?.type || 'guest'}
                    onChange={(e) => handleInputChange('type', e.target.value)}
                    className="text-sm text-primary uppercase bg-transparent border border-primary/50 rounded px-2 py-1 focus:border-primary outline-none"
                  >
                    <option value="alfr3d">Alfr3d</option>
                    <option value="HW">HW</option>
                    <option value="guest">Guest</option>
                    <option value="light">Light</option>
                    <option value="resident">Resident</option>
                  </select>
                </div>
              ) : (
                <>
                  <h2 className="text-2xl font-bold text-primary">{device?.name}</h2>
                  <p className="text-sm text-primary uppercase">{device?.type}</p>
                </>
              )}
            </div>
          </div>
          <div className="flex items-center space-x-2">
            {!isEditing ? (
              <button
                onClick={handleEdit}
                className="p-2 text-primary hover:bg-primary/20 rounded-lg transition-colors"
                title="Edit Device"
              >
                <Edit className="w-5 h-5" />
              </button>
            ) : (
              <>
                <button
                  onClick={handleSave}
                  className="p-2 text-success hover:bg-success/20 rounded-lg transition-colors"
                  title="Save Changes"
                >
                  <Save className="w-5 h-5" />
                </button>
                <button
                  onClick={handleCancel}
                  className="p-2 text-warning hover:bg-warning/20 rounded-lg transition-colors"
                  title="Cancel Edit"
                >
                  <RotateCcw className="w-5 h-5" />
                </button>
              </>
            )}
            <button
              onClick={onClose}
              className="p-2 text-text-tertiary hover:text-primary transition-colors"
              title="Close Modal"
            >
              <X className="w-6 h-6" />
            </button>
          </div>
        </div>

        {/* Device Details */}
        <div className="mb-6 grid grid-cols-2 gap-4">
          {isEditing ? (
            <>
              <div className="space-y-2">
                <div className="text-sm text-text-secondary">
                  <span className="text-primary font-medium">IP:</span>
                  <input
                    value={editedDevice?.ip || ''}
                    onChange={(e) => handleInputChange('ip', e.target.value)}
                    className="ml-2 px-2 py-1 bg-card/50 border border-primary/30 rounded text-text-primary focus:border-primary outline-none"
                    placeholder="IP Address"
                  />
                </div>
                <div className="text-sm text-text-secondary">
                  <span className="text-primary font-medium">MAC:</span>
                  <input
                    value={editedDevice?.mac || ''}
                    onChange={(e) => handleInputChange('mac', e.target.value)}
                    className="ml-2 px-2 py-1 bg-card/50 border border-primary/30 rounded text-text-primary focus:border-primary outline-none"
                    placeholder="MAC Address"
                  />
                </div>
                <div className="text-sm text-text-secondary">
                  <span className="text-primary font-medium">State:</span>
                  <span className="ml-2">{device?.state}</span>
                </div>
              </div>
              <div className="space-y-2">
                <div className="text-sm text-text-secondary">
                  <span className="text-primary font-medium">User:</span>
                  <select
                    value={editedDevice?.user || ''}
                    onChange={(e) => handleInputChange('user', e.target.value)}
                    className="ml-2 px-2 py-1 bg-card/50 border border-primary/30 rounded text-text-primary focus:border-primary outline-none"
                  >
                    <option value="">No User</option>
                    {users?.map(user => (
                      <option key={user.id} value={user.name}>{user.name}</option>
                    ))}
                  </select>
                </div>
                <div className="text-sm text-text-secondary">
                  <span className="text-primary font-medium">Last Online:</span>
                  <span className="ml-2">{device?.last_online}</span>
                </div>
              </div>
            </>
          ) : (
            <>
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
            </>
          )}
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
  users: PropTypes.array,
  onSave: PropTypes.func,
};

export default DeviceHistoryModal;
