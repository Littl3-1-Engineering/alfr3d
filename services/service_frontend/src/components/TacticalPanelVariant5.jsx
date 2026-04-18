import PropTypes from 'prop-types';

const TacticalPanelVariant5 = ({ title, children, className = "", showGrid = false }) => {
  const amberColor = 'hsl(45, 100%, 58%)';
  const grayColor = 'hsl(0, 0%, 50%)';

  return (
    <div className={`relative bg-fui-panel border border-fui-border rounded-none ${className}`}
         style={{ boxShadow: `inset 0 0 40px rgba(0, 0, 0, 0.3)` }}>
      {/* Top bar with segmented lights */}
      <div className="flex items-center justify-between px-3 py-1 border-b border-fui-border bg-black/40">
        <div className="flex items-center space-x-1">
          {[...Array(8)].map((_, i) => (
            <div
              key={i}
              className="w-1.5 h-1.5"
              style={{
                backgroundColor: i % 3 === 0 ? amberColor : grayColor,
                opacity: i % 3 === 0 ? 0.8 : 0.3
              }}
            />
          ))}
        </div>
        <div className="flex items-center space-x-2">
          <span className="text-[10px] font-mono text-fui-text/50">SEC</span>
          <div className="w-2 h-2 rounded-sm" style={{ backgroundColor: amberColor, opacity: 0.5 }}></div>
        </div>
      </div>

      {/* Header with riveted corner style */}
      <div className="relative px-4 py-2 border-b border-fui-border/50">
        {/* Rivets */}
        <div className="absolute top-1/2 left-2 w-2 h-2 rounded-full -translate-y-1/2" style={{ backgroundColor: grayColor, boxShadow: 'inset 0 0 2px black' }} />
        <div className="absolute top-1/2 right-2 w-2 h-2 rounded-full -translate-y-1/2" style={{ backgroundColor: grayColor, boxShadow: 'inset 0 0 2px black' }} />

        <div className="flex items-center justify-center space-x-4">
          <div className="h-px flex-1 bg-gradient-to-r from-transparent via-fui-border to-transparent"></div>
          <h3 className="font-tech font-bold text-base uppercase tracking-widest text-white">
            {title}
          </h3>
          <div className="h-px flex-1 bg-gradient-to-r from-transparent via-fui-border to-transparent"></div>
        </div>
      </div>

      {/* Industrial corner frames */}
      <div className="absolute top-8 left-0 w-4 h-4 z-10">
        <div className="absolute top-0 left-0 w-full h-px" style={{ backgroundColor: grayColor }} />
        <div className="absolute top-0 left-0 w-px h-full" style={{ backgroundColor: grayColor }} />
        <div className="absolute top-1 left-1 w-2 h-0.5" style={{ backgroundColor: amberColor }} />
        <div className="absolute top-1 left-1 w-0.5 h-2" style={{ backgroundColor: amberColor }} />
      </div>
      <div className="absolute top-8 right-0 w-4 h-4 z-10">
        <div className="absolute top-0 right-0 w-full h-px" style={{ backgroundColor: grayColor }} />
        <div className="absolute top-0 right-0 w-px h-full" style={{ backgroundColor: grayColor }} />
        <div className="absolute top-1 right-1 w-2 h-0.5" style={{ backgroundColor: amberColor }} />
        <div className="absolute top-1 right-1 w-0.5 h-2" style={{ backgroundColor: amberColor }} />
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

      {/* Bottom status bar */}
      <div className="absolute bottom-0 left-0 right-0 h-2 border-t border-fui-border/30 flex items-center px-2 space-x-1">
        <div className="w-1 h-1 rounded-full animate-pulse" style={{ backgroundColor: amberColor }}></div>
        <div className="flex-1 h-px bg-fui-border/30"></div>
        <div className="text-[8px] font-mono text-fui-text/30">v5.0</div>
      </div>
    </div>
  );
};

TacticalPanelVariant5.propTypes = {
  title: PropTypes.string.isRequired,
  children: PropTypes.node,
  className: PropTypes.string,
  showGrid: PropTypes.bool,
};

export default TacticalPanelVariant5;
