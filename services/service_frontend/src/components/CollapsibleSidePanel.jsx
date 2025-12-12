import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import PropTypes from 'prop-types';

const CollapsibleSidePanel = ({
  position,
  title,
  children,
  isOpen,
  onToggle,
  onClose,
  className = "",
  tabClassName = "",
  tabTop = "0px",
  tabIndex = 0
}) => {
  const isLeft = position === 'left';

  return (
    <>
      {/* Tab */}
      <motion.div
        className={`fixed z-30 cursor-pointer ${tabClassName}`}
        style={{
          top: tabTop,
          [isLeft ? 'left' : 'right']: '0px'
        }}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={onToggle}
        tabIndex={tabIndex}
      >
        <div className="bg-fui-panel border border-fui-border rounded-none p-0.5 shadow-lg w-[20px] h-[140px] flex items-center justify-center">
          {/* Corner Markers - Only on inner edge facing screen */}
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

          {/* Title Text - Vertical */}
          <div
            className="text-fui-accent font-tech font-bold text-xs uppercase tracking-widest"
            style={{
              writingMode: 'vertical-rl',
              textOrientation: 'mixed',
              whiteSpace: 'nowrap'
            }}
          >
            {title}
          </div>
        </div>
      </motion.div>

      {/* Overlay Panel */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ x: isLeft ? -400 : 400 }}
            animate={{ x: 0 }}
            exit={{ x: isLeft ? -400 : 400 }}
            transition={{ duration: 0.3, ease: 'easeInOut' }}
            className={`fixed ${isLeft ? 'left-0' : 'right-0'} w-auto max-w-sm h-auto max-h-screen z-40 bg-fui-panel/95 backdrop-blur-md border-r border-fui-border ${className}`}
            style={{ top: tabTop }}
          >
            {/* Corner Markers */}
            <div className="absolute -top-px -left-px w-3 h-3 border-t-2 border-l-2 border-fui-accent z-10" />
            <div className="absolute -top-px -right-px w-3 h-3 border-t-2 border-r-2 border-fui-accent z-10" />
            <div className="absolute -bottom-px -left-px w-3 h-3 border-b-2 border-l-2 border-fui-accent z-10" />
            <div className="absolute -bottom-px -right-px w-3 h-3 border-b-2 border-r-2 border-fui-accent z-10" />

            {/* Close Button in Top-Right Corner */}
            <button
              onClick={onClose}
              className="absolute top-2 right-2 w-6 h-6 bg-fui-panel border border-fui-accent rounded-none flex items-center justify-center text-fui-accent hover:text-white hover:bg-fui-accent/20 transition-colors z-20"
            >
              <X className="w-4 h-4" />
            </button>

            {/* Header */}
            <div className="flex items-center px-3 py-2 bg-black/40 border-b border-fui-border">
              <h3 className="font-tech font-bold text-sm uppercase tracking-widest text-white">
                <span className="text-fui-accent mr-2">/</span>{title}
              </h3>
            </div>

            {/* Content */}
            <div className="p-4">
              <div className="text-fui-text font-mono text-xs">
                {children}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};

CollapsibleSidePanel.propTypes = {
  position: PropTypes.oneOf(['left', 'right']).isRequired,
  title: PropTypes.string.isRequired,
  children: PropTypes.node,
  isOpen: PropTypes.bool.isRequired,
  onToggle: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
  className: PropTypes.string,
  tabClassName: PropTypes.string,
  tabTop: PropTypes.string,
  tabIndex: PropTypes.number,
};

export default CollapsibleSidePanel;
