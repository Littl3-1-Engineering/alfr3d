import { useState } from 'react';
import PropTypes from 'prop-types';
import Modal from 'react-modal';
import { motion } from 'framer-motion';
import { UserPlus, X } from 'lucide-react';
import { useAuth } from '../utils/useAuth';

Modal.setAppElement('#root');

/**
 * First-run onboarding: shown instead of LoginModal while GET /api/auth/setup-status reports
 * `empty` or `unclaimed` (see todo/todo_onboarding_first_user.md). Offers two mutually exclusive
 * paths -- claim one of the pre-seeded resident/technoking rows, or create a brand-new owner
 * account -- since a normal login attempt can never succeed against an unclaimed system.
 */
const OnboardingModal = ({ isOpen, onClose, setupStatus = null, onSetupComplete = undefined }) => {
  const { claim, bootstrap } = useAuth();
  const claimableUsers = setupStatus?.claimable_users || [];
  const canClaim = claimableUsers.length > 0;

  const [mode, setMode] = useState(canClaim ? 'claim' : 'create');
  const [selectedUsername, setSelectedUsername] = useState(claimableUsers[0]?.username || '');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const resetFields = () => {
    setUsername('');
    setPassword('');
    setError(null);
  };

  const handleClose = () => {
    resetFields();
    onClose();
  };

  const switchMode = (nextMode) => {
    setMode(nextMode);
    resetFields();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (mode === 'claim') {
        await claim(selectedUsername, password);
      } else {
        await bootstrap(username, password);
      }
      resetFields();
      onSetupComplete?.();
      onClose();
    } catch (err) {
      setError(err.message || 'Setup failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onRequestClose={handleClose}
      className="modal-content"
      overlayClassName="modal-overlay"
      contentLabel="Welcome to ALFR3D"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.9 }}
        className="glass rounded-2xl p-6 border border-primary/30 bg-card/20 max-w-sm w-full"
      >
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center space-x-3">
            <UserPlus className="w-6 h-6 text-primary" />
            <h2 className="text-xl font-bold text-primary">Welcome to ALFR3D</h2>
          </div>
          <button
            onClick={handleClose}
            className="p-2 text-text-tertiary hover:text-primary transition-colors"
            title="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <p className="text-sm text-text-secondary mb-4">
          {setupStatus?.state === 'empty'
            ? "Nobody's set up an account yet. Let's create one."
            : 'Residents are already set up. Claim your account, or create a new admin account.'}
        </p>

        {canClaim && (
          <div className="flex mb-4 rounded-lg overflow-hidden border border-primary/30">
            <button
              type="button"
              onClick={() => switchMode('claim')}
              className={`flex-1 py-2 text-sm font-medium transition-colors ${
                mode === 'claim'
                  ? 'bg-primary text-text-inverse'
                  : 'bg-card/50 text-text-secondary hover:text-primary'
              }`}
            >
              Claim Existing
            </button>
            <button
              type="button"
              onClick={() => switchMode('create')}
              className={`flex-1 py-2 text-sm font-medium transition-colors ${
                mode === 'create'
                  ? 'bg-primary text-text-inverse'
                  : 'bg-card/50 text-text-secondary hover:text-primary'
              }`}
            >
              Create New
            </button>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === 'claim' ? (
            <div>
              <label className="text-sm text-text-secondary block mb-1" htmlFor="onboarding-user">
                Account
              </label>
              <select
                id="onboarding-user"
                value={selectedUsername}
                onChange={(e) => setSelectedUsername(e.target.value)}
                className="w-full px-3 py-2 bg-card/50 border border-primary/30 rounded text-text-primary focus:border-primary outline-none"
                required
              >
                {claimableUsers.map((u) => (
                  <option key={u.id} value={u.username}>
                    {u.username} ({u.type})
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div>
              <label
                className="text-sm text-text-secondary block mb-1"
                htmlFor="onboarding-username"
              >
                Username
              </label>
              <input
                id="onboarding-username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-3 py-2 bg-card/50 border border-primary/30 rounded text-text-primary focus:border-primary outline-none"
                autoComplete="username"
                required
              />
            </div>
          )}
          <div>
            <label className="text-sm text-text-secondary block mb-1" htmlFor="onboarding-password">
              Password
            </label>
            <input
              id="onboarding-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 bg-card/50 border border-primary/30 rounded text-text-primary focus:border-primary outline-none"
              autoComplete="new-password"
              minLength={8}
              required
            />
          </div>

          {error && <p className="text-sm text-error">{error}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="w-full py-2 rounded-lg bg-primary text-text-inverse font-medium hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? 'Setting up…' : mode === 'claim' ? 'Claim Account' : 'Create Account'}
          </button>
        </form>
      </motion.div>
    </Modal>
  );
};

OnboardingModal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  setupStatus: PropTypes.shape({
    state: PropTypes.oneOf(['empty', 'unclaimed', 'claimed']),
    claimable_users: PropTypes.arrayOf(
      PropTypes.shape({
        id: PropTypes.number,
        username: PropTypes.string,
        type: PropTypes.string,
      })
    ),
  }),
  onSetupComplete: PropTypes.func,
};

export default OnboardingModal;
