import { motion } from 'framer-motion';
import { useState } from 'react';
import Routines from '../components/Routines';
import Personality from '../components/Personality';
import Integrations from '../components/Integrations';
import System from '../components/System';

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
      className="min-h-screen p-8"
    >
      <div className="max-w-7xl mx-auto">
        <motion.h1
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2, duration: 0.5 }}
          className="text-4xl font-bold text-cyan-400 mb-8 text-center drop-shadow-lg"
        >
          ALFR3D Matrix
        </motion.h1>
        
        <div className="flex">
          {/* Vertical Tabs */}
          <div className="w-64 mr-8">
            <div className="glass rounded-2xl p-4">
              {tabs.map((tab, index) => (
                <motion.button
                  key={tab.id}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.1, duration: 0.3 }}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full text-left py-3 px-4 rounded-lg mb-2 transition-all duration-300 ${
                    activeTab === tab.id
                      ? 'bg-cyan-400/20 text-cyan-400 border-l-4 border-cyan-400 drop-shadow-lg'
                      : 'text-gray-400 hover:text-cyan-400 hover:bg-slate-700/30'
                  }`}
                >
                  {tab.label}
                </motion.button>
              ))}
            </div>
          </div>
          
          {/* Content */}
          <div className="flex-1">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3 }}
              className="glass rounded-2xl p-6 min-h-[600px]"
            >
              {ActiveComponent && <ActiveComponent />}
            </motion.div>
          </div>
        </div>
      </div>
    </motion.div>
  );
};

export default Matrix;