import { motion, AnimatePresence } from 'framer-motion';
import { X, Settings, RefreshCw } from 'lucide-react';
import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { API_BASE_URL } from '../config';

const ControlBlade = ({ device, onClose, style }) => {
  const [power, setPower] = useState(device?.active || device?.last_state?.on || false);
  const [brightness, setBrightness] = useState(device?.last_state?.brightness || 75);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (device?.last_state) {
      setPower(device.last_state.on || false);
      setBrightness(device.last_state.brightness || 75);
    }
  }, [device?.last_state]);

  const handlePowerToggle = async () => {
    const newPowerState = !power;
    setPower(newPowerState);

    if (device?.id && device?.source) {
      setLoading(true);
      try {
        const response = await fetch(`${API_BASE_URL}/api/iot/devices/${device.id}/control`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            command: newPowerState ? 'turn_on' : 'turn_off'
          })
        });
        if (!response.ok) {
          setPower(!newPowerState);
        }
      } catch (error) {
        console.error('Error toggling power:', error);
        setPower(!newPowerState);
      } finally {
        setLoading(false);
      }
    }
  };

  const handleBrightnessChange = async (value) => {
    const newBrightness = parseInt(value, 10);
    const oldBrightness = brightness;
    setBrightness(newBrightness);

    if (device?.id && device?.source && newBrightness !== oldBrightness) {
      setLoading(true);
      try {
        const response = await fetch(`${API_BASE_URL}/api/iot/devices/${device.id}/control`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            command: 'set_brightness',
            params: { brightness: newBrightness }
          })
        });
        if (!response.ok) {
          setBrightness(oldBrightness);
        }
      } catch (error) {
        console.error('Error changing brightness:', error);
        setBrightness(oldBrightness);
      } finally {
        setLoading(false);
      }
    }
  };

  const isSmartHomeDevice = device?.source !== undefined;

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
               <div className="flex items-center space-x-2">
                 <span className="text-text-secondary">Power</span>
                 {loading && <RefreshCw className="w-4 h-4 text-primary animate-spin" />}
               </div>
               <motion.button
                 whileTap={{ scale: 0.95 }}
                 onClick={handlePowerToggle}
                 disabled={loading || !isSmartHomeDevice}
                 className={`w-12 h-6 rounded-full p-1 transition-colors ${
                   power ? 'bg-primary' : 'bg-border-secondary'
                 } ${(!isSmartHomeDevice) ? 'opacity-50 cursor-not-allowed' : ''}`}
               >
                 <motion.div
                   animate={{ x: power ? 18 : 0 }}
                   className="w-4 h-4 bg-text-inverse rounded-full"
                 />
               </motion.button>
             </div>

             {/* Brightness Slider */}
             {(device.type === 'light' || device.device_type?.includes('LIGHT')) && (
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
                   onChange={(e) => handleBrightnessChange(e.target.value)}
                   disabled={!isSmartHomeDevice || loading}
                   className={`w-full h-2 bg-border-secondary rounded-lg appearance-none cursor-pointer slider ${
                     (!isSmartHomeDevice || loading) ? 'opacity-50 cursor-not-allowed' : ''
                   }`}
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

              {/* Device Info */}
              {isSmartHomeDevice && (
                <div className="text-xs text-text-tertiary space-y-1">
                  <p>Source: {device.source === 'homeassistant' ? 'Home Assistant' : device.source === 'smartthings' ? 'SmartThings' : 'Unknown'}</p>
                  <p>Room: {device.room || 'Unknown'}</p>
                  <p>Type: {device.device_type}</p>
                  <p>Online: {device.online ? 'Yes' : 'No'}</p>
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

ControlBlade.propTypes = {
  device: PropTypes.object.isRequired,
  onClose: PropTypes.func.isRequired,
  style: PropTypes.object,
};

export default ControlBlade;
