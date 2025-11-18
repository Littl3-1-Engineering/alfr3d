import { motion } from 'framer-motion';
import { useState, lazy, Suspense } from 'react';
import PersonnelRoster from '../components/PersonnelRoster';
import EnvironmentSettings from '../components/EnvironmentSettings';
import ControlBlade from '../components/ControlBlade';

const Blueprint = lazy(() => import('../components/Blueprint'));

const Domain = () => {
  const [activeView, setActiveView] = useState('blueprint');
  const [selectedDevice, setSelectedDevice] = useState(null);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.8 }}
      className="min-h-screen p-8"
    >
      <div className="max-w-7xl mx-auto">
        <motion.h1
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2, duration: 0.5 }}
          className="text-4xl font-bold text-primary mb-8 text-center drop-shadow-lg"
        >
          ALFR3D Domain
        </motion.h1>

        {/* Sub-navigation */}
        <div className="flex justify-center mb-8">
          <div className="glass rounded-full p-1 flex space-x-1">
            <button
              onClick={() => setActiveView('blueprint')}
              className={`px-6 py-2 rounded-full transition-all duration-300 ${
                activeView === 'blueprint'
                  ? 'bg-primary/20 text-primary drop-shadow-lg'
                  : 'text-text-tertiary hover:text-primary'
              }`}
            >
              Blueprint
            </button>
            <button
              onClick={() => setActiveView('personnel')}
              className={`px-6 py-2 rounded-full transition-all duration-300 ${
                activeView === 'personnel'
                  ? 'bg-primary/20 text-primary drop-shadow-lg'
                  : 'text-text-tertiary hover:text-primary'
              }`}
            >
              Personnel
            </button>
            <button
              onClick={() => setActiveView('environment')}
              className={`px-6 py-2 rounded-full transition-all duration-300 ${
                activeView === 'environment'
                  ? 'bg-primary/20 text-primary drop-shadow-lg'
                  : 'text-text-tertiary hover:text-primary'
              }`}
            >
              Environment
            </button>
          </div>
        </div>

        <div className="relative">
          {activeView === 'blueprint' && (
            <Suspense fallback={<div className="text-center py-8">Loading Blueprint...</div>}>
              <Blueprint onDeviceSelect={setSelectedDevice} />
            </Suspense>
          )}
          {activeView === 'personnel' && (
            <PersonnelRoster />
          )}
          {activeView === 'environment' && <EnvironmentSettings />}

          <ControlBlade device={selectedDevice} onClose={() => setSelectedDevice(null)} />
        </div>
      </div>
    </motion.div>
  );
};

export default Domain;