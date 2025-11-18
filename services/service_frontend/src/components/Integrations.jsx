import { motion } from 'framer-motion';
import { CheckCircle, AlertTriangle, Settings, Mail, Map, Calendar, Music } from 'lucide-react';

const integrations = [
  { id: 1, name: 'Google Assistant', icon: Settings, status: 'connected', description: 'Voice commands and smart home integration' },
  { id: 2, name: 'Alexa', icon: Settings, status: 'requires_attention', description: 'Amazon Echo compatibility' },
  { id: 3, name: 'HomeKit', icon: Settings, status: 'connected', description: 'Apple Home app integration' },
  { id: 4, name: 'IFTTT', icon: Settings, status: 'connected', description: 'Applet automation' },
  { id: 5, name: 'Google Gmail', icon: Mail, status: 'not_connected', description: 'Email notifications and unread count' },
  { id: 6, name: 'Google Maps', icon: Map, status: 'not_connected', description: 'Travel time and directions for events' },
  { id: 7, name: 'Google Calendar', icon: Calendar, status: 'not_connected', description: 'Upcoming events and scheduling' },
  { id: 8, name: 'Spotify', icon: Music, status: 'not_connected', description: 'Music playlist suggestions' },
];

const Integrations = () => {
  const getStatusColor = (status) => {
    switch (status) {
      case 'connected': return 'text-success';
      case 'requires_attention': return 'text-warning';
      case 'not_connected': return 'text-error';
      default: return 'text-text-tertiary';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'connected': return <CheckCircle className="w-5 h-5 text-success" />;
      case 'requires_attention': return <AlertTriangle className="w-5 h-5 text-warning" />;
      case 'not_connected': return <Settings className="w-5 h-5 text-error" />;
      default: return <Settings className="w-5 h-5 text-text-tertiary" />;
    }
  };

  return (
    <div>
      <h2 className="text-2xl font-bold text-primary mb-6 drop-shadow-lg">Third-Party Integrations</h2>
      
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
              <div className="w-12 h-12 rounded-full bg-primary/20 flex items-center justify-center text-primary drop-shadow-lg">
                <integration.icon className="w-6 h-6" />
              </div>
              {getStatusIcon(integration.status)}
            </div>

            <h3 className="text-lg font-semibold text-text-primary mb-2">{integration.name}</h3>
            <p className="text-sm text-text-tertiary mb-4">{integration.description}</p>
            
            <div className="flex items-center justify-between">
              <span className={`text-sm font-medium ${getStatusColor(integration.status)}`}>
                {integration.status === 'connected' ? 'Connected' :
                 integration.status === 'requires_attention' ? 'Requires Attention' :
                 'Not Connected'}
              </span>
              <button className="px-4 py-2 bg-card/50 rounded-lg text-text-secondary hover:bg-card-hover/50 transition-colors">
                {integration.status === 'not_connected' ? 'Integrate' : 'Configure'}
              </button>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
};

export default Integrations;