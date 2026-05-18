import { motion, AnimatePresence } from 'framer-motion';
import PropTypes from 'prop-types';

const CollapsibleSidePanel = ({
  position,
  title,
  children,
  isOpen,
  onToggle,
  className = "",
  tabClassName = "",
  tabIndex = 0
}) => {
  const isLeft = position === 'left';

  return (
    <>
       {/* Tab */}
        <motion.div
          className={`fixed z-30 cursor-pointer ${tabClassName}`}
          style={{
            top: `${80 + tabIndex * 160}px`,
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
           initial={{ x: isLeft ? -1100 : 1100 }}
           animate={{ x: 0 }}
           exit={{ x: isLeft ? -1100 : 1100 }}
             transition={{ duration: 0.3, ease: 'easeInOut' }}
              className={`absolute ${isLeft ? 'left-0' : 'right-0'} w-auto max-w-4xl z-40 bg-fui-panel/95 backdrop-blur-md border-r border-fui-border ${className}`}
              style={{ top: `${80 + tabIndex * 180}px`, marginLeft: isLeft ? '30px' : 'auto', marginRight: isLeft ? 'auto' : '30px' }}
           >

            {/* Content */}
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
  title: PropTypes.string.isRequired,
  children: PropTypes.node,
  isOpen: PropTypes.bool.isRequired,
  onToggle: PropTypes.func.isRequired,
  className: PropTypes.string,
  tabClassName: PropTypes.string,
  tabIndex: PropTypes.number,
};

export default CollapsibleSidePanel;
