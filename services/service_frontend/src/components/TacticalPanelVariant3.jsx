import PropTypes from 'prop-types';

const TacticalPanelVariant3 = ({ title, children, className = "", showGrid = false }) => {
  return (
    <div className={`relative bg-fui-panel border border-fui-border rounded-none shadow-[0_0_15px_rgba(234,179,8,0.4)] ${className}`}>
      {/* Enhanced layered corner markers */}
      <div className="absolute -top-px -left-px w-4 h-4 border-t-2 border-l-2 border-fui-accent z-10">
        <div className="absolute top-1 left-1 w-2 h-2 border-t border-l border-fui-accent/60" />
      </div>
      <div className="absolute -top-px -right-px w-4 h-4 border-t-2 border-r-2 border-fui-accent z-10">
        <div className="absolute top-1 right-1 w-2 h-2 border-t border-r border-fui-accent/60" />
      </div>
      <div className="absolute -bottom-px -left-px w-4 h-4 border-b-2 border-l-2 border-fui-accent z-10">
        <div className="absolute bottom-1 left-1 w-2 h-2 border-b border-l border-fui-accent/60" />
      </div>
      <div className="absolute -bottom-px -right-px w-4 h-4 border-b-2 border-r-2 border-fui-accent z-10">
        <div className="absolute bottom-1 right-1 w-2 h-2 border-b border-r border-fui-accent/60" />
      </div>

      {/* Gradient header */}
      <div className="flex items-center justify-between px-3 py-1 border-b border-fui-border" style={{ background: 'linear-gradient(90deg, hsla(0, 0%, 40%, 0.4), hsla(0, 0%, 40%, 0.2))' }}>
        <div className="flex space-x-1">
          <div className="w-6 h-1 bg-fui-border"></div>
          <div className="w-3 h-1 bg-fui-accent"></div>
          <div className="w-1 h-1 bg-fui-accent"></div>
        </div>
        {title && (
           <h3 className="font-tech font-bold text-base uppercase tracking-widest text-white text-right">
            <span className="text-fui-accent mr-2">/</span>{title}
          </h3>
        )}
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

TacticalPanelVariant3.propTypes = {
  title: PropTypes.string,
  children: PropTypes.node,
  className: PropTypes.string,
  showGrid: PropTypes.bool,
};

export default TacticalPanelVariant3;
