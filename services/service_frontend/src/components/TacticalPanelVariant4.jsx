import PropTypes from 'prop-types';

const TacticalPanelVariant4 = ({ title, children, className = "", showGrid = false }) => {
  const amberColor = 'hsl(45, 100%, 58%)';

  return (
    <div className={`relative bg-fui-panel border border-fui-border rounded-none ${className}`}>
      {/* Scanline overlay effect */}
      <div className="absolute inset-0 pointer-events-none opacity-[0.03] z-20"
           style={{ background: `repeating-linear-gradient(0deg, transparent, transparent 2px, ${amberColor} 2px, ${amberColor} 4px)` }} />

      {/* Corner Markers - Green terminal style */}
      <div className="absolute -top-px -left-px w-4 h-4 z-10">
        <div className="absolute top-0 left-0 w-full h-0.5" style={{ backgroundColor: amberColor }} />
        <div className="absolute top-0 left-0 h-full w-0.5" style={{ backgroundColor: amberColor }} />
        <div className="absolute top-1 left-1 text-[8px]" style={{ color: amberColor }}>┌</div>
      </div>
      <div className="absolute -top-px -right-px w-4 h-4 z-10">
        <div className="absolute top-0 right-0 w-full h-0.5" style={{ backgroundColor: amberColor }} />
        <div className="absolute top-0 right-0 h-full w-0.5" style={{ backgroundColor: amberColor }} />
        <div className="absolute top-1 right-1 text-[8px]" style={{ color: amberColor }}>┐</div>
      </div>
      <div className="absolute -bottom-px -left-px w-4 h-4 z-10">
        <div className="absolute bottom-0 left-0 w-full h-0.5" style={{ backgroundColor: amberColor }} />
        <div className="absolute bottom-0 left-0 h-full w-0.5" style={{ backgroundColor: amberColor }} />
        <div className="absolute bottom-1 left-1 text-[8px]" style={{ color: amberColor }}>└</div>
      </div>
      <div className="absolute -bottom-px -right-px w-4 h-4 z-10">
        <div className="absolute bottom-0 right-0 w-full h-0.5" style={{ backgroundColor: amberColor }} />
        <div className="absolute bottom-0 right-0 h-full w-0.5" style={{ backgroundColor: amberColor }} />
        <div className="absolute bottom-1 right-1 text-[8px]" style={{ color: amberColor }}>┘</div>
      </div>

      {/* Header - Terminal style with blinking cursor */}
      <div className="flex items-center justify-between px-3 py-1 border-b border-fui-border bg-black/60">
        <h3 className="font-mono font-bold text-base uppercase tracking-widest text-white">
          <span style={{ color: amberColor }}>&gt;</span> {title}<span className="animate-pulse" style={{ color: amberColor }}>_</span>
        </h3>
        <div className="flex items-center space-x-2">
          <div className="w-2 h-2 rounded-full animate-pulse" style={{ backgroundColor: amberColor, boxShadow: `0 0 8px ${amberColor}` }}></div>
          <div className="w-12 h-0.5 bg-fui-border relative overflow-hidden">
            <div className="absolute top-0 left-0 h-full w-1/2 animate-[scan_2s_linear_infinite]" style={{ backgroundColor: amberColor }} />
          </div>
        </div>
      </div>

      {/* Content Area */}
      <div className="p-4 relative">
        {/* Optional Grid Background */}
        {showGrid && (
          <div className="absolute inset-0 bg-tech-grid bg-[length:20px_20px] opacity-5 pointer-events-none" />
        )}

        {/* Content */}
        <div className="relative z-10 text-fui-text font-mono text-xs" style={{ color: amberColor, opacity: 0.9 }}>
          {children}
        </div>
      </div>
    </div>
  );
};

TacticalPanelVariant4.propTypes = {
  title: PropTypes.string.isRequired,
  children: PropTypes.node,
  className: PropTypes.string,
  showGrid: PropTypes.bool,
};

export default TacticalPanelVariant4;
