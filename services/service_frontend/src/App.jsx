import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useEffect } from 'react'; // <--- 1. IMPORT useEffect
import Nexus from './pages/Nexus';
import Domain from './pages/Domain';
import Matrix from './pages/Matrix';
import AudioPlayer from './components/AudioPlayer';

function App() {

  // +++ 2. ADD THIS useEffect HOOK +++
  useEffect(() => {
    // Add the class to the body tag when the component mounts
    document.body.classList.add('grid-bg');

    // Optional: Return a cleanup function to remove the class if the component unmounts
    return () => {
      document.body.classList.remove('grid-bg');
    };
  }, []); // The empty array [] ensures this effect runs only once

  return (
    <Router>
      <AudioPlayer />
      <div className="min-h-screen relative overflow-hidden">
        {/* Temporary Navbar */}
        <nav className="fixed top-0 left-0 right-0 z-20 bg-card/80 backdrop-blur-sm border-b border-primary/20">
          <div className="max-w-7xl mx-auto px-4 py-3">
            <div className="flex space-x-6">
              <a href="/" className="text-primary hover:text-primary-hover transition-colors">Nexus</a>
              <a href="/domain" className="text-primary hover:text-primary-hover transition-colors">Domain</a>
              <a href="/matrix" className="text-primary hover:text-primary-hover transition-colors">Matrix</a>
            </div>
          </div>
        </nav>
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 1 }}
          className="relative z-10 pt-16" // Add padding-top to account for fixed navbar
        >
          <Routes>
            <Route path="/" element={<Nexus />} />
            <Route path="/domain" element={<Domain />} />
            <Route path="/matrix" element={<Matrix />} />
          </Routes>
        </motion.div>
      </div>
    </Router>
  );
}

export default App;
