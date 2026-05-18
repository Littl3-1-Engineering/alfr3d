import { BrowserRouter as Router, useLocation, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AudioPlayer from './components/AudioPlayer';
import socket from './utils/socket';
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

const PageLoader = () => (
  <div className="flex items-center justify-center min-h-screen">
    <div className="text-center">
      <div className="w-12 h-12 border-4 border-fui-accent border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
      <p className="text-fui-text font-mono text-sm">[ LOADING... ]</p>
    </div>
  </div>
);

function AppContent() {
  const location = useLocation();

  const getComponent = () => {
    switch (location.pathname) {
      case '/domain': return <Domain />;
      case '/matrix': return <Matrix />;
      default: return <Nexus />;
    }
  };

  return (
    <div className="min-h-screen relative overflow-hidden">
      <nav className="fixed top-0 left-0 right-0 z-20 bg-card/80 backdrop-blur-sm border-b border-primary/20">
        <div className="max-w-7xl mx-auto px-4 py-3">
          <div className="flex space-x-6">
            <Link to="/" className="text-primary hover:text-primary-hover transition-colors">Nexus</Link>
            <Link to="/domain" className="text-primary hover:text-primary-hover transition-colors">Domain</Link>
            <Link to="/matrix" className="text-primary hover:text-primary-hover transition-colors">Matrix</Link>
          </div>
        </div>
      </nav>
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
