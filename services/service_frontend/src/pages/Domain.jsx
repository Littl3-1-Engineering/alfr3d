import { motion } from 'framer-motion';
import { useState } from 'react';
import Blueprint from '../components/Blueprint';
import PersonnelRoster from '../components/PersonnelRoster';
import ControlBlade from '../components/ControlBlade';

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
          className="text-4xl font-bold text-cyan-400 mb-8 text-center drop-shadow-lg"
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
                  ? 'bg-cyan-400/20 text-cyan-400 drop-shadow-lg'
                  : 'text-gray-400 hover:text-cyan-400'
              }`}
            >
              Blueprint
            </button>
            <button
              onClick={() => setActiveView('personnel')}
              className={`px-6 py-2 rounded-full transition-all duration-300 ${
                activeView === 'personnel'
                  ? 'bg-cyan-400/20 text-cyan-400 drop-shadow-lg'
                  : 'text-gray-400 hover:text-cyan-400'
              }`}
            >
              Personnel
            </button>
          </div>
        </div>
        
        <div className="relative">
          {activeView === 'blueprint' && (
            <Blueprint onDeviceSelect={setSelectedDevice} />
          )}
          {activeView === 'personnel' && (
            <PersonnelRoster />
          )}
          
          <ControlBlade device={selectedDevice} onClose={() => setSelectedDevice(null)} />
        </div>
      </div>
    </motion.div>
  );
};

export default Domain;