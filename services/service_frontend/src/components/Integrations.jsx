import { motion } from 'framer-motion';
import { CheckCircle, AlertTriangle, Settings } from 'lucide-react';

const integrations = [
  { id: 1, name: 'Google Assistant', logo: 'G', status: 'connected', description: 'Voice commands and smart home integration' },
  { id: 2, name: 'Alexa', logo: 'A', status: 'requires_attention', description: 'Amazon Echo compatibility' },
  { id: 3, name: 'HomeKit', logo: 'H', status: 'connected', description: 'Apple Home app integration' },
  { id: 4, name: 'IFTTT', logo: 'I', status: 'connected', description: 'Applet automation' },
];

const Integrations = () => {
  const getStatusColor = (status) => {
    switch (status) {
      case 'connected': return 'text-green-400';
      case 'requires_attention': return 'text-yellow-400';
      default: return 'text-gray-400';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'connected': return <CheckCircle className="w-5 h-5 text-green-400" />;
      case 'requires_attention': return <AlertTriangle className="w-5 h-5 text-yellow-400" />;
      default: return <Settings className="w-5 h-5 text-gray-400" />;
    }
  };

  return (
    <div>
      <h2 className="text-2xl font-bold text-cyan-400 mb-6 drop-shadow-lg">Third-Party Integrations</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {integrations.map((integration, index) => (
          <motion.div
            key={integration.id}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: index * 0.1, duration: 0.5 }}
            whileHover={{ scale: 1.03 }}
            className="glass rounded-2xl p-6 cursor-pointer"
          >
            <div className="flex items-center justify-between mb-4">
              <div className="w-12 h-12 rounded-full bg-cyan-400/20 flex items-center justify-center text-cyan-400 font-bold text-xl drop-shadow-lg">
                {integration.logo}
              </div>
              {getStatusIcon(integration.status)}
            </div>
            
            <h3 className="text-lg font-semibold text-gray-200 mb-2">{integration.name}</h3>
            <p className="text-sm text-gray-400 mb-4">{integration.description}</p>
            
            <div className="flex items-center justify-between">
              <span className={`text-sm font-medium ${getStatusColor(integration.status)}`}>
                {integration.status === 'connected' ? 'Connected' : 'Requires Attention'}
              </span>
              <button className="px-4 py-2 bg-slate-700/50 rounded-lg text-gray-300 hover:bg-slate-600/50 transition-colors">
                Configure
              </button>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
};

export default Integrations;