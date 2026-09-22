import { motion, AnimatePresence } from 'framer-motion';
import PropTypes from 'prop-types';
import { useEffect } from 'react';

// Two ways in, one panel. The launcher ring around the Nexus Core opens these by default
// (2026-09-20), and an open panel's node holds its selected state so the ring doubles as
// the "what is open" indicator. `showTab` brings back the vertical-text edge tab the ring
// replaced, for people who would rather read a label than learn a silhouette — Matrix >
// Customizations > Nexus Navigation picks between them.
//
// The close control and Escape stay on in BOTH modes. The ring left no other way out (a
// wide panel can cover the Core, so "click the launcher again" is not on its own a safe
// exit), and with the tab showing they are simply a second, closer way to dismiss.
const CollapsibleSidePanel = ({
  position,
  title,
  children,
  isOpen,
  onClose,
  className = "",
  slot = 0,
  showTab = false,
  onToggle = null
}) => {
  const isLeft = position === 'left';

  useEffect(() => {
    if (!isOpen) return undefined;
    const onKeyDown = (event) => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  return (
    <>
      {showTab && onToggle && (
        <motion.button
          type="button"
          // Tabs sit tighter than the panels they open (160px vs 180px): they are 140px
          // tall strips, and matching the panel pitch left a visible gap in the column.
          className="fixed z-30 cursor-pointer bg-fui-panel border border-fui-border rounded-none p-0.5 shadow-lg w-[20px] h-[140px] flex items-center justify-center"
          style={{
            top: `${80 + slot * 160}px`,
            [isLeft ? 'left' : 'right']: '0px'
          }}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={onToggle}
          // Just the title, not "Close <title>": while the panel is open the corner close
          // control already owns that name, and two buttons answering to it made the pair
          // ambiguous. `aria-expanded` carries the open/closed state instead.
          aria-expanded={isOpen}
          aria-label={title}
        >
          {/* Corner markers, only on the inner edge facing the screen */}
          {isLeft ? (
            <>
              <div className="absolute -top-px -right-px w-2 h-2 border-t border-r border-fui-accent z-10" />
              <div className="absolute -bottom-px -right-px w-2 h-2 border-b border-r border-fui-accent z-10" />
            </>
          ) : (
            <>
              <div className="absolute -top-px -left-px w-2 h-2 border-t border-l border-fui-accent z-10" />
              <div className="absolute -bottom-px -left-px w-2 h-2 border-b border-l border-fui-accent z-10" />
            </>
          )}

          <span
            className="text-fui-accent font-tech font-bold text-xs uppercase tracking-widest"
            style={{
              writingMode: 'vertical-rl',
              textOrientation: 'mixed',
              whiteSpace: 'nowrap'
            }}
          >
            {title}
          </span>
        </motion.button>
      )}

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
    </>
  );
};

CollapsibleSidePanel.propTypes = {
  position: PropTypes.oneOf(['left', 'right']).isRequired,
  // Required in both modes: it names the panel for the close control and, when the edge
  // tab is showing, it IS the tab's label.
  title: PropTypes.string.isRequired,
  children: PropTypes.node,
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  className: PropTypes.string,
  // Which vertical slot this panel occupies on its side. Was called `tabIndex`, which
  // shadowed the DOM attribute.
  slot: PropTypes.number,
  // Render the vertical edge tab. Off by default -- the launcher ring is the default way in.
  showTab: PropTypes.bool,
  // Only used with `showTab`; the tab toggles rather than only closing.
  onToggle: PropTypes.func,
};

export default CollapsibleSidePanel;
