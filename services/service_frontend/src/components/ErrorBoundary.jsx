import { Component } from 'react';
import PropTypes from 'prop-types';

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center p-4 bg-boot-bg rounded border border-red-500/30 min-h-[200px]">
          <div className="text-center">
            <p className="text-red-400 font-mono text-xs mb-2">COMPONENT ERROR</p>
            <p className="text-red-400/60 font-mono text-[10px] max-w-[300px] truncate">
              {this.state.error?.message || 'Unknown error'}
            </p>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="mt-3 px-3 py-1 text-[10px] font-mono text-red-400 border border-red-400/30 rounded hover:bg-red-400/10 transition-colors"
            >
              RETRY
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

ErrorBoundary.propTypes = {
  children: PropTypes.node.isRequired,
};

export default ErrorBoundary;
