import { motion } from 'framer-motion';
import { useState, lazy, Suspense } from 'react';
import PersonnelRoster from '../components/PersonnelRoster';
import EnvironmentSettings from '../components/EnvironmentSettings';
import ControlBlade from '../components/ControlBlade';
import TacticalPanel from '../components/TacticalPanel';

const Blueprint = lazy(() => import('../components/Blueprint'));

const Domain = () => {
  const [activeView, setActiveView] = useState('blueprint');
  const [selectedDevice, setSelectedDevice] = useState(null);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.8 }}
      className="min-h-screen p-8 bg-fui-bg"
      style={{
        backgroundImage: "linear-gradient(to right, #222 1px, transparent 1px), linear-gradient(to bottom, #222 1px, transparent 1px)",
        backgroundSize: '20px 20px'
      }}
    >
      <div className="max-w-7xl mx-auto">
        <motion.h1
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2, duration: 0.5 }}
          className="text-4xl font-tech font-bold text-fui-accent mb-8 text-center uppercase tracking-widest"
        >
          ALFR3D Domain
        </motion.h1>

        {/* Sub-navigation */}
        <div className="flex justify-center mb-8">
          <div className="bg-fui-panel border border-fui-border p-1 flex space-x-1">
            <button
              onClick={() => setActiveView('blueprint')}
              className={`px-6 py-2 rounded-none transition-all duration-300 font-mono text-sm ${
                activeView === 'blueprint'
                  ? 'bg-fui-accent text-fui-bg font-bold'
                  : 'text-fui-text hover:text-fui-accent hover:bg-fui-dim'
              }`}
            >
              [ BLUEPRINT ]
            </button>
            <button
              onClick={() => setActiveView('personnel')}
              className={`px-6 py-2 rounded-none transition-all duration-300 font-mono text-sm ${
                activeView === 'personnel'
                  ? 'bg-fui-accent text-fui-bg font-bold'
                  : 'text-fui-text hover:text-fui-accent hover:bg-fui-dim'
              }`}
            >
              [ PERSONNEL ]
            </button>
            <button
              onClick={() => setActiveView('environment')}
              className={`px-6 py-2 rounded-none transition-all duration-300 font-mono text-sm ${
                activeView === 'environment'
                  ? 'bg-fui-accent text-fui-bg font-bold'
                  : 'text-fui-text hover:text-fui-accent hover:bg-fui-dim'
              }`}
            >
              [ ENVIRONMENT ]
            </button>
          </div>
        </div>

        <div className="relative">
          {activeView === 'blueprint' && (
            <Suspense fallback={<div className="text-center py-8 text-fui-text font-mono">[ LOADING BLUEPRINT... ]</div>}>
              <TacticalPanel title="System Blueprint" showGrid={true}>
                <Blueprint onDeviceSelect={setSelectedDevice} />
              </TacticalPanel>
            </Suspense>
          )}
          {activeView === 'personnel' && (
            <TacticalPanel title="Personnel Roster">
              <PersonnelRoster />
            </TacticalPanel>
          )}
          {activeView === 'environment' && (
            <TacticalPanel title="Environment Settings">
              <EnvironmentSettings />
            </TacticalPanel>
          )}

          <ControlBlade device={selectedDevice} onClose={() => setSelectedDevice(null)} />
        </div>
      </div>
    </motion.div>
  );
};

export default Domain;
