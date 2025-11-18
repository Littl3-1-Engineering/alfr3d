import { motion, AnimatePresence } from 'framer-motion';
import { X, Power, Settings } from 'lucide-react';
import { useState } from 'react';

const ControlBlade = ({ device, onClose, style }) => {
  const [power, setPower] = useState(device?.active || false);
  const [brightness, setBrightness] = useState(75);

  return (
    <AnimatePresence>
      {device && (
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.9 }}
          transition={{ duration: 0.2 }}
          className="absolute w-80 glass z-50 p-6 rounded-2xl shadow-lg"
          style={style}
        >
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl font-bold text-primary drop-shadow-lg">{device.name}</h2>
            <button
              onClick={onClose}
              className="p-2 rounded-full hover:bg-card-hover transition-colors"
            >
              <X className="w-5 h-5 text-text-secondary" />
            </button>
          </div>
          
           <div className="space-y-6">
             {/* Power Toggle */}
             <div className="flex items-center justify-between">
               <span className="text-text-secondary">Power</span>
               <motion.button
                 whileTap={{ scale: 0.95 }}
                 onClick={() => setPower(!power)}
                 className={`w-12 h-6 rounded-full p-1 transition-colors ${
                   power ? 'bg-primary' : 'bg-border-secondary'
                 }`}
               >
                 <motion.div
                   animate={{ x: power ? 18 : 0 }}
                   className="w-4 h-4 bg-text-inverse rounded-full"
                 />
               </motion.button>
             </div>
            
             {/* Brightness Slider */}
             {device.type === 'light' && (
               <div>
                 <div className="flex justify-between mb-2">
                   <span className="text-text-secondary">Brightness</span>
                   <span className="text-primary font-mono">{brightness}%</span>
                 </div>
                 <input
                   type="range"
                   min="0"
                   max="100"
                   value={brightness}
                   onChange={(e) => setBrightness(e.target.value)}
                   className="w-full h-2 bg-border-secondary rounded-lg appearance-none cursor-pointer slider"
                 />
               </div>
             )}
            
             {/* Device-specific controls */}
             {device.type === 'thermostat' && (
               <div>
                 <div className="flex justify-between mb-2">
                   <span className="text-text-secondary">Temperature</span>
                   <span className="text-primary font-mono">22°C</span>
                 </div>
                 <div className="flex space-x-2">
                   <button className="flex-1 py-2 bg-card rounded-lg text-text-secondary hover:bg-card-hover transition-colors">-</button>
                   <button className="flex-1 py-2 bg-card rounded-lg text-text-secondary hover:bg-card-hover transition-colors">+</button>
                 </div>
               </div>
             )}
            
             {/* Settings */}
             <button className="w-full flex items-center justify-center space-x-2 py-3 bg-card/50 rounded-lg hover:bg-card-hover/50 transition-colors">
               <Settings className="w-5 h-5 text-primary" />
               <span className="text-text-secondary">Advanced Settings</span>
             </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default ControlBlade;