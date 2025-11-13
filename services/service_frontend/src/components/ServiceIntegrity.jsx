import { motion } from 'framer-motion';
import { Activity, Users, Home, Zap } from 'lucide-react';

const services = [
  { name: 'User Service', status: 'healthy', icon: Users, value: 95 },
  { name: 'Device Service', status: 'warning', icon: Activity, value: 78 },
  { name: 'Environment', status: 'healthy', icon: Home, value: 92 },
  { name: 'Daemon', status: 'healthy', icon: Zap, value: 88 },
];

const ServiceIntegrity = () => {
  return (
    <div className="glass rounded-2xl p-6">
      <h2 className="text-xl font-bold text-cyan-400 mb-4 drop-shadow-lg">Service Integrity</h2>
      <div className="space-y-4">
        {services.map((service, index) => (
          <motion.div
            key={service.name}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.1, duration: 0.5 }}
            className="flex items-center space-x-3"
          >
            <service.icon className={`w-6 h-6 ${service.status === 'healthy' ? 'text-cyan-400' : 'text-yellow-400'} drop-shadow-lg`} />
            <div className="flex-1">
              <div className="flex justify-between text-sm">
                <span className="text-gray-300">{service.name}</span>
                <span className="text-cyan-400 font-mono">{service.value}%</span>
              </div>
              <motion.div
                className="w-full bg-slate-700 rounded-full h-2 mt-1"
                initial={{ width: 0 }}
                animate={{ width: '100%' }}
                transition={{ delay: 0.5 + index * 0.1, duration: 1 }}
              >
                <motion.div
                  className={`h-2 rounded-full ${service.status === 'healthy' ? 'bg-cyan-400' : 'bg-yellow-400'}`}
                  initial={{ width: 0 }}
                  animate={{ width: `${service.value}%` }}
                  transition={{ delay: 0.7 + index * 0.1, duration: 1.5, ease: "easeOut" }}
                  style={{
                    boxShadow: `0 0 10px ${service.status === 'healthy' ? '#06b6d4' : '#fbbf24'}`
                  }}
                />
              </motion.div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
};

export default ServiceIntegrity;