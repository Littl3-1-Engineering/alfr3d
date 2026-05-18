import PropTypes from 'prop-types';

const TacticalPanelVariant6 = ({ title, children, className = "", showGrid = false }) => {
  const silverColor = 'hsl(210, 20%, 80%)';
  const amberColor = 'hsl(45, 100%, 58%)';

  return (
    <div className={`relative bg-fui-panel border border-fui-border/60 rounded-none ${className}`} style={{ boxShadow: `0 0 10px rgba(245, 158, 11, 0.1)` }}>
      {/* Minimalist corner accents - thin lines */}
      <div className="absolute top-0 left-0 w-8 h-px z-10" style={{ backgroundColor: silverColor }} />
      <div className="absolute top-0 left-0 w-px h-8 z-10" style={{ backgroundColor: silverColor }} />
      <div className="absolute top-0 right-0 w-8 h-px z-10" style={{ backgroundColor: silverColor }} />
      <div className="absolute top-0 right-0 w-px h-8 z-10" style={{ backgroundColor: silverColor }} />
      <div className="absolute bottom-0 left-0 w-8 h-px z-10" style={{ backgroundColor: silverColor }} />
      <div className="absolute bottom-0 left-0 w-px h-8 z-10" style={{ backgroundColor: silverColor }} />
      <div className="absolute bottom-0 right-0 w-8 h-px z-10" style={{ backgroundColor: silverColor }} />
      <div className="absolute bottom-0 right-0 w-px h-8 z-10" style={{ backgroundColor: silverColor }} />

      {/* Minimalist header - just text with subtle accent */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-fui-border/40 bg-gradient-to-r from-transparent via-fui-border/20 to-transparent">
        <div className="flex-1 h-px bg-gradient-to-r from-transparent to-transparent" style={{ background: `linear-gradient(90deg, transparent, ${amberColor}, transparent)` }} />
        <h3 className="px-4 font-tech font-medium text-sm uppercase tracking-[0.2em] text-white/90">
          <span style={{ color: amberColor }}>::</span> {title} <span style={{ color: amberColor }}>::</span>
        </h3>
        <div className="flex-1 h-px bg-gradient-to-r from-transparent to-transparent" style={{ background: `linear-gradient(90deg, transparent, ${amberColor}, transparent)` }} />
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

TacticalPanelVariant6.propTypes = {
  title: PropTypes.string.isRequired,
  children: PropTypes.node,
  className: PropTypes.string,
  showGrid: PropTypes.bool,
};

export default TacticalPanelVariant6;
