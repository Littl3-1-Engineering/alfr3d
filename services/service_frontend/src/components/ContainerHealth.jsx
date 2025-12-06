import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';

const ContainerHealth = () => {
  const [selectedContainer, setSelectedContainer] = useState(null);
  const [containers, setContainers] = useState([]);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    const fetchContainers = async () => {
      try {
        setError(false);
        const response = await fetch(API_BASE_URL + '/api/containers');
        const data = await response.json();
        console.log('Fetched containers for ContainerHealth:', data);
        setContainers(data);
      } catch (error) {
        console.error('Error fetching containers for ContainerHealth:', error);
        setError(true);
      } finally {
        setHasLoaded(true);
      }
    };
    fetchContainers();
    const interval = setInterval(fetchContainers, 10000); // Update every 10 seconds
    return () => clearInterval(interval);
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6 }}
      className="relative bg-fui-panel rounded-none"
    >

      {/* Content Area */}
      <div className="p-2 relative pt-4">
        {!hasLoaded ? (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-fui-panel border border-fui-border rounded-none p-4 text-center"
          >
            <p className="text-fui-accent font-mono uppercase text-sm">LOADING CONTAINER DATA...</p>
          </motion.div>
        ) : error && containers.length === 0 ? (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-fui-panel border border-fui-border rounded-none p-4 text-center"
          >
            <p className="text-red-400 font-mono uppercase text-sm">CONTAINER DATA UNAVAILABLE</p>
          </motion.div>
        ) : containers.length === 0 ? (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-fui-panel border border-fui-border rounded-none p-4 text-center"
          >
            <p className="text-red-400 font-mono uppercase text-sm">CONTAINERS FAILURE</p>
          </motion.div>
        ) : (
          <div className="flex flex-col gap-4">
            {containers.map((container, index) => (
        <motion.div
          key={container.name}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: index * 0.1, duration: 0.5 }}
          whileHover={{ scale: 1.02 }}
          onClick={() => setSelectedContainer(container)}
          className="cursor-pointer p-3 border border-fui-border/30 hover:border-fui-accent/50 transition-colors duration-200"
        >
          <div className="flex justify-between items-center mb-2">
            <span className="text-sm font-mono font-bold text-fui-text">{container.name}</span>
              {container.errors > 0 ? (
                <div className="w-3 h-3 border-2 border-error" />
              ) : (
                <div className="w-3 h-3 border-2 border-fui-accent bg-fui-accent" />
              )}
          </div>

          {/* <div className="grid grid-cols-3 gap-2 text-xs mb-2">
            <div className="flex items-center space-x-1">
              <span className="text-fui-text font-mono">CPU:</span>
              <span className="text-fui-text font-mono">{container.cpu}%</span>
            </div>
            <div className="flex items-center space-x-1">
              <span className="text-fui-text font-mono">MEM:</span>
              <span className="text-fui-text font-mono">{container.mem}%</span>
            </div>
            <div className="flex items-center space-x-1">
              <span className="text-fui-text font-mono">DSK:</span>
              <span className="text-fui-text font-mono">{container.disk}%</span>
            </div>
          </div> */}

          {/* Progress bars */}
          <div className="space-y-1">
            <div className="w-full bg-fui-border/20 h-1">
                <motion.div
                  className="bg-fui-accent h-1"
                  initial={{ width: 0 }}
                   animate={{ width: Math.min(container.cpu, 100) + '%' }}
                  transition={{ delay: 0.5 + index * 0.1, duration: 1 }}
                />
            </div>
            <div className="w-full bg-fui-border/20 h-1">
                <motion.div
                  className="bg-fui-text h-1"
                  initial={{ width: 0 }}
                   animate={{ width: Math.min(container.mem, 100) + '%' }}
                  transition={{ delay: 0.6 + index * 0.1, duration: 1 }}
                />
            </div>
            <div className="w-full bg-fui-border/20 h-1">
                <motion.div
                  className="bg-warning h-1"
                  initial={{ width: 0 }}
                   animate={{ width: Math.min(container.disk, 100) + '%' }}
                  transition={{ delay: 0.7 + index * 0.1, duration: 1 }}
                />
            </div>
          </div>
        </motion.div>
      ))}

      {selectedContainer && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="p-3 border border-fui-accent/50 bg-fui-dim"
        >
          <h3 className="text-sm font-mono font-bold text-fui-accent mb-2">[ {selectedContainer.name.toUpperCase()} ]</h3>
          <p className="text-xs text-fui-text font-mono">ERRORS: {selectedContainer.errors}</p>
        </motion.div>
      )}
          </div>
        )}
      </div>
    </motion.div>
  );
};

export default ContainerHealth;
