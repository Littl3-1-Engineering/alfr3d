import { motion } from 'framer-motion';
import { useState, lazy, Suspense } from 'react';
import { Loader2 } from 'lucide-react';
import TacticalPanel from '../components/TacticalPanel';

const Routines = lazy(() => import('../components/Routines'));
const Personality = lazy(() => import('../components/Personality'));
const Integrations = lazy(() => import('../components/Integrations'));
const System = lazy(() => import('../components/System'));

const LoadingFallback = () => (
  <div className="flex items-center justify-center h-64">
    <Loader2 className="w-8 h-8 text-fui-accent animate-spin" />
    <span className="ml-3 text-text-tertiary">Loading...</span>
  </div>
);

const Matrix = () => {
  const [activeTab, setActiveTab] = useState('routines');

  const tabs = [
    { id: 'routines', label: 'Routines', component: Routines },
    { id: 'personality', label: 'Personality', component: Personality },
    { id: 'integrations', label: 'Integrations', component: Integrations },
    { id: 'system', label: 'System', component: System },
  ];

  const ActiveComponent = tabs.find(tab => tab.id === activeTab)?.component;

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
          className="text-4xl font-tech font-bold text-fui-accent mb-4 text-center uppercase tracking-widest"
        >
          ALFR3D Matrix
        </motion.h1>

        <div className="flex">
          {/* Vertical Tabs */}
          <div className="w-64 mr-8">
            <TacticalPanel title="Systems" className="p-0">
              <div className="p-4">
                {tabs.map((tab, index) => (
                  <motion.button
                    key={tab.id}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.1, duration: 0.3 }}
                    onClick={() => setActiveTab(tab.id)}
                    className={`w-full text-left py-3 px-4 rounded-none mb-2 transition-all duration-300 font-mono text-sm border-l-2 ${
                      activeTab === tab.id
                        ? 'bg-fui-accent text-fui-bg border-fui-accent font-bold'
                        : 'text-fui-text border-fui-border hover:text-fui-accent hover:bg-fui-dim'
                    }`}
                  >
                    [ {tab.label.toUpperCase()} ]
                  </motion.button>
                ))}
              </div>
            </TacticalPanel>
          </div>

          {/* Content */}
          <div className="flex-1">
            <TacticalPanel title={tabs.find(tab => tab.id === activeTab)?.label || 'System'} className="min-h-[600px]">
              <motion.div
                key={activeTab}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3 }}
              >
                <Suspense fallback={<LoadingFallback />}>
                  {ActiveComponent && <ActiveComponent />}
                </Suspense>
              </motion.div>
            </TacticalPanel>
          </div>
        </div>
      </div>
    </motion.div>
  );
};

export default Matrix;
