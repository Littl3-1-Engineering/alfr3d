import PropTypes from 'prop-types';

const TacticalPanelVariant7 = ({ title, children, className = "", showGrid = false }) => {
  const amberColor = 'hsl(45, 100%, 58%)';

  return (
    <div className={`relative bg-fui-panel border border-fui-border rounded-none ${className}`}
         style={{
           background: 'linear-gradient(180deg, rgba(245, 158, 11, 0.02) 0%, rgba(0, 0, 0, 0) 100%)',
           boxShadow: `0 0 15px rgba(245, 158, 11, 0.1)`
         }}>
      {/* Glitch effect horizontal lines */}
      <div className="absolute top-2 left-0 right-0 h-px z-10 opacity-50"
           style={{ background: `linear-gradient(90deg, transparent 0%, ${amberColor} 20%, ${amberColor} 80%, transparent 100%)` }} />
      <div className="absolute bottom-2 left-0 right-0 h-px z-10 opacity-50"
           style={{ background: `linear-gradient(90deg, transparent 0%, ${amberColor} 20%, ${amberColor} 80%, transparent 100%)` }} />

      {/* Diagonal corner brackets */}
      <div className="absolute -top-px -left-px w-6 h-6 z-10 overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-px transform -rotate-45" style={{ backgroundColor: amberColor, boxShadow: `0 0 6px ${amberColor}` }} />
        <div className="absolute top-2 left-2 text-[10px] font-mono" style={{ color: amberColor }}>┏</div>
      </div>
      <div className="absolute -top-px -right-px w-6 h-6 z-10 overflow-hidden">
        <div className="absolute top-0 right-0 w-full h-px transform rotate-45" style={{ backgroundColor: amberColor, boxShadow: `0 0 6px ${amberColor}` }} />
        <div className="absolute top-2 right-2 text-[10px] font-mono" style={{ color: amberColor }}>┓</div>
      </div>
      <div className="absolute -bottom-px -left-px w-6 h-6 z-10 overflow-hidden">
        <div className="absolute bottom-0 left-0 w-full h-px transform rotate-45" style={{ backgroundColor: amberColor, boxShadow: `0 0 6px ${amberColor}` }} />
        <div className="absolute bottom-2 left-2 text-[10px] font-mono" style={{ color: amberColor }}>┗</div>
      </div>
      <div className="absolute -bottom-px -right-px w-6 h-6 z-10 overflow-hidden">
        <div className="absolute bottom-0 right-0 w-full h-px transform -rotate-45" style={{ backgroundColor: amberColor, boxShadow: `0 0 6px ${amberColor}` }} />
        <div className="absolute bottom-2 right-2 text-[10px] font-mono" style={{ color: amberColor }}>┛</div>
      </div>

      {/* Header - Holographic style */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-fui-border/50"
           style={{
             background: `linear-gradient(90deg, transparent 0%, rgba(245, 158, 11, 0.05) 50%, transparent 100%)`,
             borderImage: `linear-gradient(90deg, transparent, ${amberColor}, transparent) 1`
           }}>
        <div className="flex items-center space-x-2">
          <div className="w-3 h-3 border" style={{ borderColor: amberColor, transform: 'rotate(45deg)' }}></div>
          <div className="h-2 w-16 bg-gradient-to-r from-fui-border to-transparent"></div>
        </div>
        <h3 className="font-tech font-bold text-base uppercase tracking-widest text-white"
            style={{ textShadow: `0 0 8px ${amberColor}` }}>
          <span style={{ color: amberColor }}>♦</span> {title}
        </h3>
        <div className="flex items-center space-x-2">
          <div className="h-2 w-16 bg-gradient-to-l from-fui-border to-transparent"></div>
          <div className="w-2 h-2 rounded-sm" style={{ backgroundColor: amberColor, boxShadow: `0 0 8px ${amberColor}` }}></div>
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

TacticalPanelVariant7.propTypes = {
  title: PropTypes.string.isRequired,
  children: PropTypes.node,
  className: PropTypes.string,
  showGrid: PropTypes.bool,
};

export default TacticalPanelVariant7;
