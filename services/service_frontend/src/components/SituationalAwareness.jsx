import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import { Clock, Thermometer, Droplets, Wind, Sun, Moon } from 'lucide-react';

const SituationalAwareness = () => {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const isDay = time.getHours() >= 6 && time.getHours() < 18;

  return (
    <div className="glass rounded-2xl p-6 border border-cyan-500/30 bg-slate-800/20">
      <h2 className="text-xl font-bold text-cyan-400 mb-4 drop-shadow-lg">Situational Awareness</h2>

      <div className="space-y-4">
        {/* Time */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center space-x-3"
        >
          {isDay ? <Sun className="w-6 h-6 text-yellow-400 drop-shadow-lg" /> : <Moon className="w-6 h-6 text-cyan-400 drop-shadow-lg" />}
          <div>
            <p className="text-sm text-gray-400">Current Time</p>
            <p className="text-lg font-mono text-gray-200">{time.toLocaleTimeString()}</p>
          </div>
        </motion.div>

        {/* Weather */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="flex items-center space-x-3"
        >
          <Thermometer className="w-6 h-6 text-red-400 drop-shadow-lg" />
          <div>
            <p className="text-sm text-gray-400">Temperature</p>
            <p className="text-lg font-mono text-gray-200">72°F</p>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="flex items-center space-x-3"
        >
          <Droplets className="w-6 h-6 text-blue-400 drop-shadow-lg" />
          <div>
            <p className="text-sm text-gray-400">Humidity</p>
            <p className="text-lg font-mono text-gray-200">45%</p>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="flex items-center space-x-3"
        >
          <Wind className="w-6 h-6 text-green-400 drop-shadow-lg" />
          <div>
            <p className="text-sm text-gray-400">Wind Speed</p>
            <p className="text-lg font-mono text-gray-200">5 mph</p>
          </div>
        </motion.div>
      </div>
    </div>
  );
};

export default SituationalAwareness;