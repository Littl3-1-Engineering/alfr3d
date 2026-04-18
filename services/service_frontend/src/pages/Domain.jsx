import { motion } from 'framer-motion';
import { useState, lazy, Suspense, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import PersonnelRoster from '../components/PersonnelRoster';
import EnvironmentSettings from '../components/EnvironmentSettings';
import ControlBlade from '../components/ControlBlade';
import TacticalPanelVariant1 from '../components/TacticalPanelVariant1';
import TacticalPanelVariant2 from '../components/TacticalPanelVariant2';
import TacticalPanelVariant3 from '../components/TacticalPanelVariant3';

const Blueprint = lazy(() => import('../components/Blueprint'));

const Domain = () => {
  const [searchParams] = useSearchParams();
  const tabParam = searchParams.get('tab');
  const userIdParam = searchParams.get('userId');

  const [activeView, setActiveView] = useState(tabParam === 'personnel' ? 'personnel' : 'blueprint');
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [initialUserId, setInitialUserId] = useState(userIdParam);

  useEffect(() => {
    if (userIdParam && !initialUserId) {
      setInitialUserId(userIdParam);
    }
  }, [tabParam, userIdParam, initialUserId]);

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
              <TacticalPanelVariant1 title="System Blueprint" showGrid={true}>
                <Blueprint onDeviceSelect={setSelectedDevice} />
              </TacticalPanelVariant1>
            </Suspense>
          )}
           {activeView === 'personnel' && (
              <TacticalPanelVariant2 title="Personnel Roster">
                <PersonnelRoster initialUserId={initialUserId} />
              </TacticalPanelVariant2>
            )}
           {activeView === 'environment' && (
              <TacticalPanelVariant3 title="Environment Settings">
                <EnvironmentSettings />
              </TacticalPanelVariant3>
            )}

          <ControlBlade device={selectedDevice} onClose={() => setSelectedDevice(null)} />
        </div>
      </div>
    </motion.div>
  );
};

export default Domain;
