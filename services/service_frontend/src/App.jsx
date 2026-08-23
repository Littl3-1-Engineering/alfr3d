import { BrowserRouter as Router, useLocation, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LogIn, LogOut } from 'lucide-react';
import AudioPlayer from './components/AudioPlayer';
import LoginModal from './components/LoginModal';
import SignInRequired from './components/SignInRequired';
import socket from './utils/socket';
import { useAuth } from './utils/useAuth';
import Nexus from './pages/Nexus';
import Domain from './pages/Domain';
import Matrix from './pages/Matrix';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      gcTime: 10 * 60 * 1000,
      refetchOnWindowFocus: false,
      retry: 1
    }
  }
});

function AppContent() {
  const location = useLocation();
  const { user, isAuthenticated, logout } = useAuth();
  const [loginModalOpen, setLoginModalOpen] = useState(false);

  const getComponent = () => {
    switch (location.pathname) {
      case '/domain':
        return isAuthenticated
          ? <Domain />
          : <SignInRequired pageName="Domain" onSignIn={() => setLoginModalOpen(true)} />;
      case '/matrix':
        return isAuthenticated
          ? <Matrix />
          : <SignInRequired pageName="Matrix" onSignIn={() => setLoginModalOpen(true)} />;
      default: return <Nexus />;
    }
  };

  return (
    <div className="min-h-screen relative overflow-hidden">
      <nav className="fixed top-0 left-0 right-0 z-20 bg-card/80 backdrop-blur-sm border-b border-primary/20">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex space-x-6">
            <Link to="/" className="text-primary hover:text-primary-hover transition-colors">Nexus</Link>
            {isAuthenticated && (
              <>
                <Link to="/domain" className="text-primary hover:text-primary-hover transition-colors">Domain</Link>
                <Link to="/matrix" className="text-primary hover:text-primary-hover transition-colors">Matrix</Link>
              </>
            )}
          </div>
          {isAuthenticated ? (
            <div className="flex items-center space-x-3">
              <span className="text-sm text-text-secondary">
                {user.id} <span className="text-primary uppercase">{user.role}</span>
              </span>
              <button
                onClick={logout}
                className="flex items-center space-x-1 text-sm text-text-secondary hover:text-primary transition-colors"
                title="Sign Out"
              >
                <LogOut className="w-4 h-4" />
                <span>Sign Out</span>
              </button>
            </div>
          ) : (
            <button
              onClick={() => setLoginModalOpen(true)}
              className="flex items-center space-x-1 text-sm text-primary hover:text-primary-hover transition-colors"
            >
              <LogIn className="w-4 h-4" />
              <span>Sign In</span>
            </button>
          )}
        </div>
      </nav>
      <LoginModal isOpen={loginModalOpen} onClose={() => setLoginModalOpen(false)} />
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1 }}
        className="relative z-10 pt-16"
      >
        {getComponent()}
      </motion.div>
    </div>
  );
}

function App() {

  useEffect(() => {
    document.body.classList.add('grid-bg');
    socket.connect();

    return () => {
      document.body.classList.remove('grid-bg');
      socket.close();
    };
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <AudioPlayer />
        <AppContent />
      </Router>
    </QueryClientProvider>
  );
}

export default App;
