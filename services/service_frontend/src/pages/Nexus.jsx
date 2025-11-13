import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import Core from '../components/Core';
import SituationalAwareness from '../components/SituationalAwareness';
import OnlineUsers from '../components/OnlineUsers';
import ContainerHealth from '../components/ContainerHealth';
import EventStream from '../components/EventStream';

const Nexus = () => {
  const [systemHealth, setSystemHealth] = useState('cyan');

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
          ALFR3D Nexus
        </motion.h1>
        
        <div className="flex flex-row gap-8 flex-wrap justify-center items-center">
          {/* Left Panels */}
          <motion.div
            initial={{ opacity: 0, x: -50 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.4, duration: 0.6 }}
            className="flex flex-col gap-6 w-full lg:w-80"
          >
            <SituationalAwareness />
            <OnlineUsers />
          </motion.div>

          {/* Center Core */}
          <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.6, duration: 0.8 }}
            className="flex-1 flex flex-col justify-center items-center gap-8"
          >
            <Core health={systemHealth} />
            <EventStream />
          </motion.div>

          {/* Right Panels */}
          <motion.div
            initial={{ opacity: 0, x: 50 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.8, duration: 0.6 }}
            className="flex flex-col gap-6 w-full lg:w-80"
          >
            <ContainerHealth />
          </motion.div>
        </div>


      </div>
    </motion.div>
  );
};

export default Nexus;