import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { API_BASE_URL } from '../config';
import socket from '../utils/socket';
import { containerStatus, statusColor, utilization } from '../utils/containerStatus';

const ContainerHealth = ({ initialContainers = null }) => {
  const [selectedContainer, setSelectedContainer] = useState(null);
  const [containers, setContainers] = useState(initialContainers || []);
  const [hasLoaded, setHasLoaded] = useState(!!initialContainers);
  const [error, setError] = useState(false);

  const fetchContainers = async () => {
    try {
      setError(false);
      const response = await fetch(API_BASE_URL + '/api/containers');
      if (response.ok) {
        const data = await response.json();
        setContainers(data);
      } else {
        setError(true);
      }
    } catch (error) {
      console.error('Error fetching containers for ContainerHealth:', error);
      setError(true);
    }
  };

  useEffect(() => {
    if (initialContainers && initialContainers.length > 0) {
      setContainers(initialContainers);
      setHasLoaded(true);
    } else {
      fetchContainers().finally(() => setHasLoaded(true));
    }
  }, [initialContainers]);

  useEffect(() => {
    const handleContainersUpdate = (data) => {
      setContainers(data);
      setHasLoaded(true);
    };

    socket.on('containers', handleContainersUpdate);

    return () => {
      socket.off('containers', handleContainersUpdate);
    };
  }, []);

  const renderBar = (container, index) => {
    // The bar shows how hard the container is working; its colour shows whether Docker
    // considers it well. A container can legitimately be busy and green at the same time.
    const util = utilization(container);
    const color = statusColor(container);
    const status = containerStatus(container);

    return (
      <motion.div
        key={container.name}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: index * 0.05, duration: 0.4 }}
        whileHover={{ scale: 1.01 }}
        onClick={() => setSelectedContainer(container)}
        className="group relative cursor-pointer p-2 border border-fui-border/30 hover:border-fui-accent/50 transition-colors duration-200"
      >
        <div className="flex justify-between items-center mb-1.5">
          <span className="text-xs font-mono font-bold text-fui-text truncate mr-2">{container.name}</span>
          <span className="flex items-center gap-2 shrink-0">
            <span className="text-[9px] font-mono tracking-widest" style={{ color }}>
              {status}
            </span>
            <span className="text-xs font-mono text-fui-text">{Math.round(util)}%</span>
          </span>
        </div>

        {/* Full-width utilization bar */}
        <div className="w-full h-2 bg-fui-border/20 relative overflow-hidden">
          <motion.div
            className="h-full"
            style={{ backgroundColor: color, boxShadow: `0 0 8px ${color}` }}
            initial={{ width: 0 }}
            animate={{ width: `${util}%` }}
            transition={{ delay: 0.3 + index * 0.08, duration: 0.9, ease: 'easeOut' }}
          />
        </div>

        {/* Hover tooltip */}
        <div className="absolute right-0 top-full mt-1 z-20 hidden group-hover:block bg-fui-panel border border-fui-border p-2 shadow-xl whitespace-nowrap">
          <p className="font-mono text-[10px] text-fui-text">
            <span className="text-fui-text/60">CPU:</span> <span style={{ color: 'var(--theme-primary)' }}>{container.cpu}%</span>{' '}
            <span className="ml-2 text-fui-text/60">MEM:</span> <span style={{ color: 'var(--theme-primary)' }}>{container.mem}%</span>
          </p>
          <p className="font-mono text-[10px] text-fui-text mt-1">
            <span className="text-fui-text/60">STATE:</span> <span style={{ color }}>{container.state}</span>{' '}
            <span className="ml-2 text-fui-text/60">HEALTH:</span>{' '}
            <span style={{ color }}>{container.health === 'none' ? 'no healthcheck' : container.health}</span>
          </p>
        </div>
      </motion.div>
    );
  };

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
          <div className="flex flex-col gap-2">
            {containers.map((container, index) => renderBar(container, index))}

            {selectedContainer && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="p-3 border border-fui-accent/50 bg-fui-dim mt-2"
              >
                <h3 className="text-sm font-mono font-bold text-fui-accent mb-2">[ {selectedContainer.name.toUpperCase()} ]</h3>
                <div className="space-y-1">
                  {[
                    ['CPU', selectedContainer.cpu, 'var(--theme-primary)'],
                    ['MEM', selectedContainer.mem, 'var(--theme-primary)'],
                  ].map(([label, value, color]) => (
                    <div key={label} className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-fui-text/60 w-8">{label}</span>
                      <div className="flex-1 h-1.5 bg-fui-border/20">
                        <motion.div
                          className="h-full"
                          style={{ backgroundColor: color }}
                          initial={{ width: 0 }}
                          animate={{ width: `${Math.min(value, 100)}%` }}
                          transition={{ duration: 0.8 }}
                        />
                      </div>
                      <span className="font-mono text-[10px] text-fui-text w-10 text-right">{value}%</span>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-fui-text font-mono mt-2">
                  STATE: {selectedContainer.state} &middot; HEALTH:{' '}
                  {selectedContainer.health === 'none' ? 'no healthcheck defined' : selectedContainer.health}
                  {selectedContainer.restarts > 0 && ` \u00b7 RESTARTS: ${selectedContainer.restarts}`}
                </p>
              </motion.div>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
};

ContainerHealth.propTypes = {
  initialContainers: PropTypes.array,
};

export default ContainerHealth;
