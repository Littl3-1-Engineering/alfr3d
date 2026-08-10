import { Home, User } from 'lucide-react';
import PropTypes from 'prop-types';

const ResidentsSummary = ({ residents = 0, guests = 0 }) => (
  <div className="flex items-center justify-center gap-6 px-4 py-2 border-b border-fui-border bg-fui-panel/50">
    <div className="flex items-center gap-2">
      <Home size={14} className="text-fui-accent" />
      <span className="font-mono text-xs tracking-widest">
        <span className="text-fui-text/60">RESIDENTS:</span>
        <span className="text-fui-accent ml-1">{residents}</span>
      </span>
    </div>
    <div className="flex items-center gap-2">
      <User size={14} className="text-fui-text/60" />
      <span className="font-mono text-xs tracking-widest">
        <span className="text-fui-text/60">GUESTS:</span>
        <span className="text-fui-text ml-1">{guests}</span>
      </span>
    </div>
  </div>
);

ResidentsSummary.propTypes = {
  residents: PropTypes.number,
  guests: PropTypes.number,
};

export default ResidentsSummary;
