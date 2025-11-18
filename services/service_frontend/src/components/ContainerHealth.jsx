import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import { Cpu, HardDrive, MemoryStick, AlertTriangle } from 'lucide-react';
import { API_BASE_URL } from '../config';

const ContainerHealth = () => {
  const [selectedContainer, setSelectedContainer] = useState(null);
  const [containers, setContainers] = useState([]);

  useEffect(() => {
    const fetchContainers = async () => {
      try {
        const response = await fetch(API_BASE_URL + '/api/containers');
        const data = await response.json();
        console.log('Fetched containers for ContainerHealth:', data);
        setContainers(data);
      } catch (error) {
        console.error('Error fetching containers for ContainerHealth:', error);
      }
    };
    fetchContainers();
    const interval = setInterval(fetchContainers, 10000); // Update every 10 seconds
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="glass rounded-2xl p-6 border border-primary/30 bg-card/20">
      <h2 className="text-xl font-bold text-primary mb-4 drop-shadow-lg">Container Health</h2>

      <div className="space-y-4">
        {containers.map((container, index) => (
          <motion.div
            key={container.name}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1, duration: 0.5 }}
            whileHover={{ scale: 1.02 }}
            onClick={() => setSelectedContainer(container)}
            className="cursor-pointer"
          >
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm font-semibold text-text-primary">{container.name}</span>
              {container.errors > 0 && <AlertTriangle className="w-4 h-4 text-error" />}
            </div>

            <div className="grid grid-cols-3 gap-2 text-xs">
              <div className="flex items-center space-x-1">
                <Cpu className="w-3 h-3 text-primary" />
                <span className="text-text-secondary">{container.cpu}%</span>
              </div>
              <div className="flex items-center space-x-1">
                <MemoryStick className="w-3 h-3 text-success" />
                <span className="text-text-secondary">{container.mem}%</span>
              </div>
              <div className="flex items-center space-x-1">
                <HardDrive className="w-3 h-3 text-warning" />
                <span className="text-text-secondary">{container.disk}%</span>
              </div>
            </div>

            {/* Progress bars */}
            <div className="mt-2 space-y-1">
              <div className="w-full bg-card rounded-full h-1">
                 <motion.div
                   className="bg-primary h-1 rounded-full"
                   initial={{ width: 0 }}
                    animate={{ width: Math.min(container.cpu, 100) + '%' }}
                   transition={{ delay: 0.5 + index * 0.1, duration: 1 }}
                 />
              </div>
              <div className="w-full bg-card rounded-full h-1">
                 <motion.div
                   className="bg-success h-1 rounded-full"
                   initial={{ width: 0 }}
                    animate={{ width: Math.min(container.mem, 100) + '%' }}
                   transition={{ delay: 0.6 + index * 0.1, duration: 1 }}
                 />
              </div>
              <div className="w-full bg-card rounded-full h-1">
                 <motion.div
                   className="bg-warning h-1 rounded-full"
                   initial={{ width: 0 }}
                    animate={{ width: Math.min(container.disk, 100) + '%' }}
                   transition={{ delay: 0.7 + index * 0.1, duration: 1 }}
                 />
              </div>
            </div>
          </motion.div>
        ))}
      </div>

      {selectedContainer && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mt-4 p-3 bg-card/50 rounded-lg"
        >
          <h3 className="text-sm font-semibold text-primary mb-2">{selectedContainer.name} Details</h3>
          <p className="text-xs text-text-tertiary">Errors: {selectedContainer.errors}</p>
        </motion.div>
      )}
    </div>
  );
};

export default ContainerHealth;