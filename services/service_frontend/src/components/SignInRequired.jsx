import PropTypes from 'prop-types';
import { motion } from 'framer-motion';
import { Lock, LogIn } from 'lucide-react';

const SignInRequired = ({ pageName, onSignIn }) => (
  <div className="flex items-center justify-center min-h-[60vh] px-4">
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="glass rounded-2xl p-8 border border-primary/30 bg-card/20 max-w-sm w-full text-center"
    >
      <Lock className="w-8 h-8 text-primary mx-auto mb-4" />
      <h2 className="text-xl font-bold text-primary mb-2">Sign In Required</h2>
      <p className="text-sm text-text-secondary mb-6">
        {pageName} is only visible to signed-in users.
      </p>
      <button
        onClick={onSignIn}
        className="inline-flex items-center space-x-2 px-4 py-2 bg-primary/20 border border-primary rounded-lg text-primary hover:bg-primary/30 transition-colors"
      >
        <LogIn className="w-4 h-4" />
        <span>Sign In</span>
      </button>
    </motion.div>
  </div>
);

SignInRequired.propTypes = {
  pageName: PropTypes.string.isRequired,
  onSignIn: PropTypes.func.isRequired,
};

export default SignInRequired;
