import { useState } from 'react';
import PropTypes from 'prop-types';
import Modal from 'react-modal';
import { motion } from 'framer-motion';
import { LogIn, X } from 'lucide-react';
import { useAuth } from '../utils/useAuth';

Modal.setAppElement('#root');

const LoginModal = ({ isOpen, onClose }) => {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const handleClose = () => {
    setUsername('');
    setPassword('');
    setError(null);
    onClose();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(username, password);
      handleClose();
    } catch (err) {
      setError(err.message || 'Sign in failed');
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
      contentLabel="Sign In"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.9 }}
        className="glass rounded-2xl p-6 border border-primary/30 bg-card/20 max-w-sm w-full"
      >
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center space-x-3">
            <LogIn className="w-6 h-6 text-primary" />
            <h2 className="text-xl font-bold text-primary">Sign In</h2>
          </div>
          <button
            onClick={handleClose}
            className="p-2 text-text-tertiary hover:text-primary transition-colors"
            title="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-sm text-text-secondary block mb-1" htmlFor="login-username">
              Username
            </label>
            <input
              id="login-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-3 py-2 bg-card/50 border border-primary/30 rounded text-text-primary focus:border-primary outline-none"
              autoComplete="username"
              required
            />
          </div>
          <div>
            <label className="text-sm text-text-secondary block mb-1" htmlFor="login-password">
              Password
            </label>
            <input
              id="login-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 bg-card/50 border border-primary/30 rounded text-text-primary focus:border-primary outline-none"
              autoComplete="current-password"
              required
            />
          </div>

          {error && <p className="text-sm text-error">{error}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="w-full py-2 rounded-lg bg-primary text-text-inverse font-medium hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? 'Signing in…' : 'Sign In'}
          </button>
        </form>
      </motion.div>
    </Modal>
  );
};

LoginModal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
};

export default LoginModal;
