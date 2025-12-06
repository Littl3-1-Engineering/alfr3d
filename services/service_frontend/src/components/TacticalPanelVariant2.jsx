import PropTypes from 'prop-types';

const TacticalPanelVariant2 = ({ title, children, className = "", showGrid = false }) => {
  const amberColor = 'hsl(45, 100%, 58%)';
  return (
    <div className={`relative bg-fui-panel border border-fui-border rounded-none ${className}`}>
      {/* Corner Markers - Amber */}
      <div className="absolute -top-px -left-px w-3 h-3 border-t-2 border-l-2 z-10" style={{ borderColor: amberColor }} />
      <div className="absolute -top-px -right-px w-3 h-3 border-t-2 border-r-2 z-10" style={{ borderColor: amberColor }} />
      <div className="absolute -bottom-px -left-px w-3 h-3 border-b-2 border-l-2 z-10" style={{ borderColor: amberColor }} />
      <div className="absolute -bottom-px -right-px w-3 h-3 border-b-2 border-r-2 z-10" style={{ borderColor: amberColor }} />

      {/* Header Bar - Striped amber pattern */}
      <div className="flex items-center justify-between px-3 py-1 border-b border-fui-border" style={{ background: 'repeating-linear-gradient(45deg, transparent, transparent 8px, hsla(45, 100%, 58%, 0.2) 8px, hsla(45, 100%, 58%, 0.2) 16px)' }}>
         <h3 className="font-tech font-bold text-base uppercase tracking-widest text-white">
          <span className="mr-2" style={{ color: amberColor }}> /</span>{title}
        </h3>
        <div className="flex space-x-1">
          <div className="w-4 h-1 bg-fui-border"></div>
          <div className="w-2 h-1" style={{ backgroundColor: amberColor }}></div>
          <div className="w-2 h-1 bg-fui-border"></div>
          <div className="w-1 h-1" style={{ backgroundColor: amberColor }}></div>
        </div>
      </div>

      {/* Content Area */}
      <div className="p-4 relative">
        {/* Optional Grid Background */}
        {showGrid && (
          <div className="absolute inset-0 bg-tech-grid bg-[length:20px_20px] opacity-5 pointer-events-none" />
        )}

        {/* Content */}
         <div className="relative z-10 text-fui-text font-mono text-xs">
          {children}
        </div>
      </div>
    </div>
  );
};

TacticalPanelVariant2.propTypes = {
  title: PropTypes.string.isRequired,
  children: PropTypes.node,
  className: PropTypes.string,
  showGrid: PropTypes.bool,
};

export default TacticalPanelVariant2;
