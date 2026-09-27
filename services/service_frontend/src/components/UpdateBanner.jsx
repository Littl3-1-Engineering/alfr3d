import { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { motion } from 'framer-motion';
import { ArrowUpCircle, CheckCircle2, AlertTriangle, Loader2, X } from 'lucide-react';
import { useAuth } from '../utils/useAuth';
import { useUpdateCheck } from '../utils/useUpdateCheck';
import { useUpdateStatus } from '../utils/useUpdateStatus';
import UpdateConfirmModal from './UpdateConfirmModal';

const ADMIN_ROLES = ['owner', 'technoking'];
const DISMISSED_TAG_KEY = 'alfr3d-update-banner-dismissed-tag';
const DISMISSED_STATUS_KEY = 'alfr3d-update-status-dismissed-at';
const TERMINAL_STATES = ['success', 'failed', 'rolled_back'];

const UpdateBanner = ({ onVisibilityChange }) => {
  const { isAuthenticated, user } = useAuth();
  const updateInfo = useUpdateCheck();
  const updateStatus = useUpdateStatus();
  const isAdmin = isAuthenticated && ADMIN_ROLES.includes(user?.role);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const [dismissedTag, setDismissedTag] = useState(() => {
    try {
      return sessionStorage.getItem(DISMISSED_TAG_KEY);
    } catch (e) {
      return null; // private browsing / storage blocked -- fall back to always showing
    }
  });
  const [dismissedStatusAt, setDismissedStatusAt] = useState(() => {
    try {
      return sessionStorage.getItem(DISMISSED_STATUS_KEY);
    } catch (e) {
      return null;
    }
  });

  const isRunning = updateStatus?.state === 'running';
  const isTerminal = TERMINAL_STATES.includes(updateStatus?.state) && updateStatus.updated_at !== dismissedStatusAt;
  const isAvailable = Boolean(updateInfo?.update_available && updateInfo.latest_tag !== dismissedTag);

  const visible = Boolean(isAdmin && (isRunning || isTerminal || isAvailable));

  useEffect(() => {
    onVisibilityChange?.(visible);
  }, [visible, onVisibilityChange]);

  if (!visible) return null;

  const dismissAvailable = () => {
    try {
      sessionStorage.setItem(DISMISSED_TAG_KEY, updateInfo.latest_tag);
    } catch (e) { /* nothing to persist to -- banner just won't stay dismissed this tab */ }
    setDismissedTag(updateInfo.latest_tag);
  };

  const dismissStatus = () => {
    try {
      sessionStorage.setItem(DISMISSED_STATUS_KEY, updateStatus.updated_at);
    } catch (e) { /* nothing to persist to -- banner just won't stay dismissed this tab */ }
    setDismissedStatusAt(updateStatus.updated_at);
  };

  let content;
  if (isRunning) {
    content = (
      <>
        <Loader2 className="w-4 h-4 text-primary flex-shrink-0 animate-spin" />
        <span className="text-sm text-text-primary flex-1">
          Updating to {updateStatus.target_tag}: {updateStatus.message || updateStatus.phase}
        </span>
      </>
    );
  } else if (isTerminal) {
    const isSuccess = updateStatus.state === 'success';
    const Icon = isSuccess ? CheckCircle2 : AlertTriangle;
    content = (
      <>
        <Icon className={`w-4 h-4 flex-shrink-0 ${isSuccess ? 'text-success' : 'text-error'}`} />
        <span className={`text-sm flex-1 ${isSuccess ? 'text-text-primary' : 'text-error'}`}>
          {isSuccess
            ? `Updated to ${updateStatus.target_tag}.`
            : updateStatus.message || `Update to ${updateStatus.target_tag} did not complete.`}
        </span>
        <button
          onClick={dismissStatus}
          className="text-text-secondary hover:text-primary transition-colors"
          title="Dismiss"
        >
          <X className="w-4 h-4" />
        </button>
      </>
    );
  } else {
    content = (
      <>
        <ArrowUpCircle className="w-4 h-4 text-primary flex-shrink-0" />
        <span className="text-sm text-text-primary flex-1">
          {updateInfo.latest_title || updateInfo.latest_tag} is available
          {updateInfo.current_version ? ` (currently ${updateInfo.current_version})` : ''}.
        </span>
        {updateInfo.release_notes_url && (
          <a
            href={updateInfo.release_notes_url}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-primary hover:text-primary-hover transition-colors underline"
          >
            Release notes
          </a>
        )}
        <button
          onClick={() => setConfirmOpen(true)}
          className="text-sm px-3 py-1 bg-primary/20 border border-primary rounded-lg text-primary hover:bg-primary/30 transition-colors"
        >
          Update Now
        </button>
        <button
          onClick={dismissAvailable}
          className="text-text-secondary hover:text-primary transition-colors"
          title="Later"
        >
          <X className="w-4 h-4" />
        </button>
      </>
    );
  }

  return (
    <>
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-primary/10 border-b border-primary/30 backdrop-blur-sm"
      >
        <div className="max-w-7xl mx-auto px-4 py-2 flex items-center gap-3">{content}</div>
      </motion.div>
      <UpdateConfirmModal
        isOpen={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        updateInfo={updateInfo}
      />
    </>
  );
};

UpdateBanner.propTypes = {
  onVisibilityChange: PropTypes.func,
};

export default UpdateBanner;
