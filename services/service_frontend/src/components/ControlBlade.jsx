import { motion, AnimatePresence } from 'framer-motion';
import { X, Power, Settings } from 'lucide-react';
import { useState } from 'react';

const ControlBlade = ({ device, onClose }) => {
  const [power, setPower] = useState(device?.active || false);
  const [brightness, setBrightness] = useState(75);

  return (
    <AnimatePresence>
      {device && (
        <motion.div
          initial={{ x: '100%' }}
          animate={{ x: 0 }}
          exit={{ x: '100%' }}
          transition={{ type: 'tween', duration: 0.3 }}
          className="fixed top-0 right-0 h-full w-80 glass z-50 p-6"
        >
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl font-bold text-cyan-400 drop-shadow-lg">{device.name}</h2>
            <button
              onClick={onClose}
              className="p-2 rounded-full hover:bg-slate-700/50 transition-colors"
            >
              <X className="w-5 h-5 text-gray-400" />
            </button>
          </div>
          
          <div className="space-y-6">
            {/* Power Toggle */}
            <div className="flex items-center justify-between">
              <span className="text-gray-300">Power</span>
              <motion.button
                whileTap={{ scale: 0.95 }}
                onClick={() => setPower(!power)}
                className={`w-12 h-6 rounded-full p-1 transition-colors ${
                  power ? 'bg-cyan-400' : 'bg-gray-600'
                }`}
              >
                <motion.div
                  animate={{ x: power ? 18 : 0 }}
                  className="w-4 h-4 bg-white rounded-full"
                />
              </motion.button>
            </div>
            
            {/* Brightness Slider */}
            {device.type === 'light' && (
              <div>
                <div className="flex justify-between mb-2">
                  <span className="text-gray-300">Brightness</span>
                  <span className="text-cyan-400 font-mono">{brightness}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={brightness}
                  onChange={(e) => setBrightness(e.target.value)}
                  className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer slider"
                />
              </div>
            )}
            
            {/* Device-specific controls */}
            {device.type === 'thermostat' && (
              <div>
                <div className="flex justify-between mb-2">
                  <span className="text-gray-300">Temperature</span>
                  <span className="text-cyan-400 font-mono">72°F</span>
                </div>
                <div className="flex space-x-2">
                  <button className="flex-1 py-2 bg-slate-700 rounded-lg text-gray-300 hover:bg-slate-600 transition-colors">-</button>
                  <button className="flex-1 py-2 bg-slate-700 rounded-lg text-gray-300 hover:bg-slate-600 transition-colors">+</button>
                </div>
              </div>
            )}
            
            {/* Settings */}
            <button className="w-full flex items-center justify-center space-x-2 py-3 bg-slate-700/50 rounded-lg hover:bg-slate-600/50 transition-colors">
              <Settings className="w-5 h-5 text-cyan-400" />
              <span className="text-gray-300">Advanced Settings</span>
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default ControlBlade;