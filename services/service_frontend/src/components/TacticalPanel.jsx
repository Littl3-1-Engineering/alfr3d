
import PropTypes from 'prop-types';

const TacticalPanel = ({ title, children, className = "", showGrid = false }) => {
  return (
    <div className={`relative bg-fui-panel border border-fui-border rounded-none ${className}`}>
      {/* Corner Markers - L-shaped decorations */}
      <div className="absolute -top-px -left-px w-3 h-3 border-t-2 border-l-2 border-fui-accent z-10" />
      <div className="absolute -top-px -right-px w-3 h-3 border-t-2 border-r-2 border-fui-accent z-10" />
      <div className="absolute -bottom-px -left-px w-3 h-3 border-b-2 border-l-2 border-fui-accent z-10" />
      <div className="absolute -bottom-px -right-px w-3 h-3 border-b-2 border-r-2 border-fui-accent z-10" />

      {/* Header Bar */}
      <div className="flex items-center justify-between px-3 py-1 bg-black/40 border-b border-fui-border">
        <h3 className="font-tech font-bold text-lg uppercase tracking-widest text-white">
          <span className="text-fui-accent mr-2">/</span>{title}
        </h3>
        <div className="flex space-x-1">
          <div className="w-8 h-1 bg-fui-border"></div>
          <div className="w-2 h-1 bg-fui-accent"></div>
        </div>
      </div>

      {/* Content Area */}
      <div className="p-4 relative">
        {/* Optional Grid Background */}
        {showGrid && (
          <div className="absolute inset-0 bg-tech-grid bg-[length:20px_20px] opacity-5 pointer-events-none" />
        )}

        {/* Content */}
        <div className="relative z-10 text-fui-text font-mono text-sm">
          {children}
        </div>
      </div>
    </div>
  );
};

TacticalPanel.propTypes = {
  title: PropTypes.string.isRequired,
  children: PropTypes.node,
  className: PropTypes.string,
  showGrid: PropTypes.bool,
};

export default TacticalPanel;
