import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import { Terminal, ChevronRight } from 'lucide-react';

const System = () => {
  const [logs, setLogs] = useState([
    '> System initialized',
    '> Kafka broker connected',
    '> MySQL database online',
    '> All services healthy',
    '> User authentication active',
  ]);

  useEffect(() => {
    const interval = setInterval(() => {
      const newLogs = [
        '> Device scan completed',
        '> Environment data updated',
        '> Routine executed successfully',
      ];
      setLogs(prev => [...prev, ...newLogs]);
    }, 3000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      <h2 className="text-2xl font-bold text-cyan-400 mb-6 drop-shadow-lg">System Monitor</h2>
      
      <div className="glass rounded-2xl p-6 font-mono text-sm">
        <div className="flex items-center space-x-2 mb-4">
          <Terminal className="w-5 h-5 text-cyan-400" />
          <span className="text-cyan-400">ALFR3D Terminal</span>
        </div>
        
        <div className="bg-black/50 rounded-lg p-4 h-96 overflow-y-auto">
          {logs.map((log, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: index * 0.1, duration: 0.3 }}
              className="flex items-center space-x-2 mb-1"
            >
              <ChevronRight className="w-3 h-3 text-cyan-400 flex-shrink-0" />
              <span className="text-green-400">{log}</span>
            </motion.div>
          ))}
        </div>
        
        <div className="mt-4 flex items-center space-x-2">
          <span className="text-cyan-400">alfr3d@matrix:~$</span>
          <span className="animate-pulse">_</span>
        </div>
      </div>
    </div>
  );
};

export default System;