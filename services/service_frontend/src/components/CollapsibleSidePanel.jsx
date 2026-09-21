import { motion, AnimatePresence } from 'framer-motion';
import PropTypes from 'prop-types';
import { useEffect } from 'react';

// The vertical-text edge tabs that used to open these panels are gone (2026-09-20) —
// the launcher ring around the Nexus Core opens them now, and an open panel's node holds
// its selected state, so the ring doubles as the "what is open" indicator.
//
// That removed the only way to close a panel, so this owns closing instead: a close
// control in the corner plus Escape. A wide panel can cover the Core, which means
// "click the launcher again" is not on its own a safe way out.
const CollapsibleSidePanel = ({
  position,
  title,
  children,
  isOpen,
  onClose,
  className = "",
  slot = 0
}) => {
  const isLeft = position === 'left';

  useEffect(() => {
    if (!isOpen) return undefined;
    const onKeyDown = (event) => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ x: isLeft ? -1100 : 1100 }}
          animate={{ x: 0 }}
          exit={{ x: isLeft ? -1100 : 1100 }}
          transition={{ duration: 0.3, ease: 'easeInOut' }}
          className={`absolute ${isLeft ? 'left-0' : 'right-0'} w-auto max-w-4xl z-40 bg-fui-panel/95 backdrop-blur-md border-r border-fui-border ${className}`}
          style={{ top: `${80 + slot * 180}px`, marginLeft: isLeft ? '30px' : 'auto', marginRight: isLeft ? 'auto' : '30px' }}
        >
          <button
            type="button"
            onClick={onClose}
            aria-label={`Close ${title}`}
            className="absolute top-1 right-1 z-10 w-5 h-5 flex items-center justify-center border border-fui-border text-fui-accent hover:border-fui-accent font-mono text-xs leading-none"
          >
            ×
          </button>

          <div className="text-fui-text font-mono text-xs">
            {children}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

CollapsibleSidePanel.propTypes = {
  position: PropTypes.oneOf(['left', 'right']).isRequired,
  // Still required: it names the panel for the close control's accessible name.
  title: PropTypes.string.isRequired,
  children: PropTypes.node,
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  className: PropTypes.string,
  // Which vertical slot this panel occupies on its side. Was called `tabIndex`, which
  // both described a tab that no longer exists and shadowed the DOM attribute.
  slot: PropTypes.number,
};

export default CollapsibleSidePanel;
