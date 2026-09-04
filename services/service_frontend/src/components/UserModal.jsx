import PropTypes from 'prop-types';
import { useState } from 'react';
import Modal from 'react-modal';
import { motion } from 'framer-motion';
import { User, Monitor, X, Edit, Save, RotateCcw, Trash2, KeyRound, Copy, Check } from 'lucide-react';

Modal.setAppElement('#root');

// Unambiguous charset (no 0/O/1/l/I) so a copied-then-retyped password isn't misread.
const PASSWORD_CHARS =
  'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%^&*';

function generatePassword(length = 16) {
  const values = new Uint32Array(length);
  crypto.getRandomValues(values);
  return Array.from(values, (v) => PASSWORD_CHARS[v % PASSWORD_CHARS.length]).join('');
}

const UserModal = ({ isOpen, onClose, user, devices, onDeviceClick, onSave, onDelete, isAdmin, onResetPassword }) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editedUser, setEditedUser] = useState(null);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [resetPassword, setResetPassword] = useState(null);
  const [resetError, setResetError] = useState(null);
  const [resetting, setResetting] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleEdit = () => {
    setIsEditing(true);
    setEditedUser({ ...user });
  };

  const handleCancel = () => {
    setIsEditing(false);
    setEditedUser(null);
  };

  const handleSave = async () => {
    if (onSave && editedUser) {
      const success = await onSave(editedUser);
      if (success) {
        setIsEditing(false);
        setEditedUser(null);
      }
    }
  };

  const handleInputChange = (field, value) => {
    setEditedUser(prev => ({ ...prev, [field]: value }));
  };

  const resetPasswordState = () => {
    setShowResetConfirm(false);
    setResetPassword(null);
    setResetError(null);
    setResetting(false);
    setCopied(false);
  };

  const handleClose = () => {
    resetPasswordState();
    onClose();
  };

  const handleConfirmReset = async () => {
    setResetting(true);
    setResetError(null);
    const candidate = generatePassword();
    const success = await onResetPassword(user.id, candidate);
    setResetting(false);
    if (success) {
      setShowResetConfirm(false);
      setResetPassword(candidate);
    } else {
      setResetError('Password reset failed -- please try again.');
    }
  };

  const handleCopyPassword = () => {
    navigator.clipboard.writeText(resetPassword).then(() => {
      setCopied(true);
    }).catch(() => setResetError('Could not copy automatically -- select and copy the password manually.'));
  };

  return (
    <Modal
      isOpen={isOpen}
      onRequestClose={handleClose}
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
              {isEditing ? (
                <div className="space-y-1">
                  <input
                    value={editedUser?.name || ''}
                    onChange={(e) => handleInputChange('name', e.target.value)}
                    className="text-2xl font-bold text-primary bg-transparent border-b border-primary/50 focus:border-primary outline-none"
                  />
                  <select
                    value={editedUser?.type || 'guest'}
                    onChange={(e) => handleInputChange('type', e.target.value)}
                    className="text-sm text-primary uppercase bg-transparent border border-primary/50 rounded px-2 py-1 focus:border-primary outline-none"
                  >
                    <option value="technoking">Technoking</option>
                    <option value="owner">Owner</option>
                    <option value="resident">Resident</option>
                    <option value="guest">Guest</option>
                  </select>
                </div>
              ) : (
                <>
                  <h2 className="text-2xl font-bold text-primary">{user?.name}</h2>
                  <p className="text-sm text-primary uppercase">{user?.type}</p>
                </>
              )}
            </div>
          </div>
          <div className="flex items-center space-x-2">
            {!isEditing ? (
              <>
                {isAdmin && (
                  <>
                    <button
                      onClick={handleEdit}
                      className="p-2 text-primary hover:bg-primary/20 rounded-lg transition-colors"
                      title="Edit User"
                    >
                      <Edit className="w-5 h-5" />
                    </button>
                    <button
                      onClick={() => setShowResetConfirm(true)}
                      className="p-2 text-warning hover:bg-warning/20 rounded-lg transition-colors"
                      title="Reset Password"
                    >
                      <KeyRound className="w-5 h-5" />
                    </button>
                    <button
                      onClick={() => onDelete && onDelete(user?.id)}
                      className="p-2 text-error hover:bg-error/20 rounded-lg transition-colors"
                      title="Delete User"
                    >
                      <Trash2 className="w-5 h-5" />
                    </button>
                  </>
                )}
              </>
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
              onClick={handleClose}
              className="p-2 text-text-tertiary hover:text-primary transition-colors"
              title="Close Modal"
            >
              <X className="w-6 h-6" />
            </button>
          </div>
        </div>

        {isAdmin && (showResetConfirm || resetPassword || resetError) && (
          <div className="mb-6 glass rounded-xl p-4 border border-warning/40 bg-warning/5">
            {resetPassword ? (
              <div className="space-y-3">
                <p className="text-sm text-text-secondary">
                  New password for <span className="text-primary font-medium">{user?.name}</span> --
                  share it with them directly, it can&apos;t be emailed yet. It won&apos;t be shown again.
                </p>
                <div className="flex items-center space-x-2">
                  <code className="flex-1 px-3 py-2 bg-card/50 border border-primary/30 rounded text-text-primary select-all break-all">
                    {resetPassword}
                  </code>
                  <button
                    onClick={handleCopyPassword}
                    className="p-2 text-primary hover:bg-primary/20 rounded-lg transition-colors shrink-0"
                    title="Copy Password"
                  >
                    {copied ? <Check className="w-5 h-5 text-success" /> : <Copy className="w-5 h-5" />}
                  </button>
                </div>
                <p className="text-xs text-text-tertiary">
                  Their existing sessions have been signed out and will need to sign back in with this password.
                </p>
                <button
                  onClick={resetPasswordState}
                  className="px-3 py-1.5 bg-border/20 border border-border rounded text-text-tertiary hover:bg-border/30 text-sm"
                >
                  Done
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-text-secondary">
                  Generate a new password for <span className="text-primary font-medium">{user?.name}</span>?
                  This signs them out of every device -- they&apos;ll need the new password to sign back in.
                </p>
                {resetError && <p className="text-sm text-error">{resetError}</p>}
                <div className="flex space-x-2">
                  <button
                    onClick={handleConfirmReset}
                    disabled={resetting}
                    className="px-4 py-1.5 bg-warning/20 border border-warning rounded text-warning hover:bg-warning/30 disabled:opacity-50 text-sm"
                  >
                    {resetting ? 'Resetting...' : 'Generate & Reset'}
                  </button>
                  <button
                    onClick={resetPasswordState}
                    className="px-4 py-1.5 bg-border/20 border border-border rounded text-text-tertiary hover:bg-border/30 text-sm"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* User Details */}
        <div className="mb-6 space-y-2">
          {isEditing ? (
            <>
              <div className="text-sm text-text-secondary">
                <span className="text-primary font-medium">Email:</span>
                <input
                  type="email"
                  value={editedUser?.email || ''}
                  onChange={(e) => handleInputChange('email', e.target.value)}
                  className="ml-2 px-2 py-1 bg-card/50 border border-primary/30 rounded text-text-primary focus:border-primary outline-none"
                  placeholder="Email address"
                />
              </div>
              <div className="text-sm text-text-secondary">
                <span className="text-primary font-medium">About:</span>
                <textarea
                  value={editedUser?.about_me || ''}
                  onChange={(e) => handleInputChange('about_me', e.target.value)}
                  className="ml-2 px-2 py-1 bg-card/50 border border-primary/30 rounded text-text-primary focus:border-primary outline-none resize-none"
                  rows={2}
                  placeholder="About this user"
                />
              </div>
              <div className="text-sm text-text-secondary">
                <span className="text-primary font-medium">How Alfred addresses them:</span>
                <input
                  value={editedUser?.title || ''}
                  onChange={(e) => handleInputChange('title', e.target.value)}
                  className="ml-2 px-2 py-1 bg-card/50 border border-primary/30 rounded text-text-primary focus:border-primary outline-none"
                  placeholder='e.g. "boss", "Dr. Athos", or leave blank to use their name'
                />
              </div>
              <div className="text-sm text-text-secondary">
                <span className="text-primary font-medium">State:</span>
                <span className="ml-2">{user?.state}</span>
              </div>
              <div className="text-sm text-text-secondary">
                <span className="text-primary font-medium">Last Online:</span>
                <span className="ml-2">{user?.last_online}</span>
              </div>
            </>
          ) : (
            <>
              <div className="text-sm text-text-secondary">
                <span className="text-primary font-medium">Email:</span> {user?.email || 'Not provided'}
              </div>
              <div className="text-sm text-text-secondary">
                <span className="text-primary font-medium">About:</span> {user?.about_me || 'Not provided'}
              </div>
              <div className="text-sm text-text-secondary">
                <span className="text-primary font-medium">How Alfred addresses them:</span> {user?.title || 'Not set (uses name)'}
              </div>
              <div className="text-sm text-text-secondary">
                <span className="text-primary font-medium">State:</span> {user?.state}
              </div>
              <div className="text-sm text-text-secondary">
                <span className="text-primary font-medium">Last Online:</span> {user?.last_online}
              </div>
            </>
          )}
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
                  <div>IP: {device.IP}</div>
                  <div>MAC: {device.MAC}</div>
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
  onSave: PropTypes.func,
  onDelete: PropTypes.func,
  isAdmin: PropTypes.bool,
  onResetPassword: PropTypes.func,
};

export default UserModal;
