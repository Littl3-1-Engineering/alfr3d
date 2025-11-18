import PropTypes from 'prop-types';
import Modal from 'react-modal';
import { motion } from 'framer-motion';
import { User, Monitor, X } from 'lucide-react';

Modal.setAppElement('#root');

const UserModal = ({ isOpen, onClose, user, devices, onDeviceClick }) => {
  return (
    <Modal
      isOpen={isOpen}
      onRequestClose={onClose}
      className="modal-content"
      overlayClassName="modal-overlay"
      contentLabel="User Details"
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
            <User className={`w-8 h-8 ${user?.type !== 'guest' ? 'text-success' : 'text-warning'}`} />
            <div>
              <h2 className="text-2xl font-bold text-primary">{user?.name}</h2>
              <p className="text-sm text-primary uppercase">{user?.type}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-text-tertiary hover:text-primary transition-colors text-2xl"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* User Details */}
        <div className="mb-6 space-y-2">
          <div className="text-sm text-text-secondary">
            <span className="text-primary font-medium">Email:</span> {user?.email || 'Not provided'}
          </div>
          <div className="text-sm text-text-secondary">
            <span className="text-primary font-medium">About:</span> {user?.about_me || 'Not provided'}
          </div>
          <div className="text-sm text-text-secondary">
            <span className="text-primary font-medium">State:</span> {user?.state}
          </div>
          <div className="text-sm text-text-secondary">
            <span className="text-primary font-medium">Last Online:</span> {user?.last_online}
          </div>
        </div>

        {/* Devices Section */}
        <div>
          <h3 className="text-xl font-bold text-primary mb-4">
            Devices ({devices?.length || 0})
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-h-96 overflow-y-auto">
            {devices?.map((device, index) => (
              <motion.div
                key={device.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1, duration: 0.5 }}
                className="glass rounded-2xl p-4 border border-primary/30 bg-card/20 cursor-pointer hover:bg-card-hover/30 transition-colors"
                onClick={() => onDeviceClick(device)}
              >
                <div className="flex items-center justify-between mb-3">
                  <Monitor className="w-5 h-5 text-primary" />
                  <span className="text-xs text-primary uppercase">{device.type}</span>
                </div>
                <h4 className="text-sm font-semibold text-text-primary mb-2">{device.name}</h4>
                <div className="text-xs text-text-tertiary space-y-1">
                  <div>IP: {device.ip}</div>
                  <div>MAC: {device.mac}</div>
                  <div>State: {device.state}</div>
                  <div>Last Online: {device.last_online}</div>
                </div>
              </motion.div>
            ))}
            {(!devices || devices.length === 0) && (
              <div className="col-span-full text-center text-text-tertiary py-8">
                No devices found for this user
              </div>
            )}
          </div>
        </div>
      </motion.div>
    </Modal>
  );
};

UserModal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  user: PropTypes.object,
  devices: PropTypes.array,
  onDeviceClick: PropTypes.func.isRequired,
};

export default UserModal;