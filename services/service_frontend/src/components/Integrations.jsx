import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import { CheckCircle, AlertTriangle, Settings, Mail, Map, Calendar, Music, Home, Zap } from 'lucide-react';
import { API_BASE_URL } from '../config';

const baseIntegrations = [
  { id: 1, name: 'Home Assistant', icon: Home, integrationType: 'iot_ha', description: 'Local smart home control' },
  { id: 2, name: 'SmartThings', icon: Zap, integrationType: 'iot_st', description: 'Cloud-based smart home control' },
  { id: 3, name: 'Alexa', icon: Settings, integrationType: null, description: 'Amazon Echo compatibility' },
  { id: 4, name: 'HomeKit', icon: Settings, integrationType: null, description: 'Apple Home app integration' },
  { id: 5, name: 'IFTTT', icon: Settings, integrationType: null, description: 'Applet automation' },
  { id: 6, name: 'Google Gmail', icon: Mail, integrationType: 'google', description: 'Email notifications and unread count' },
  { id: 7, name: 'Google Maps', icon: Map, integrationType: null, description: 'Travel time and directions for events' },
  { id: 8, name: 'Google Calendar', icon: Calendar, integrationType: 'google', description: 'Upcoming events and scheduling' },
  { id: 9, name: 'Spotify', icon: Music, integrationType: null, description: 'Music playlist suggestions' },
];

const Integrations = () => {
  const [integrations, setIntegrations] = useState(baseIntegrations);
  const [syncing, setSyncing] = useState({});
  const [configModal, setConfigModal] = useState(null);
  const [configForm, setConfigForm] = useState({});

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/integrations/status`);
        const iotResponse = await fetch(`${API_BASE_URL}/api/iot/status`);

        let status = {};
        if (response.ok) {
          status = await response.json();
        }

        let iotStatus = {};
        if (iotResponse.ok) {
          iotStatus = await iotResponse.json();
        }

        setIntegrations(prev => prev.map(integration => {
          if (integration.id === 1 && iotStatus.ha) {
            return { ...integration, status: iotStatus.ha.connected ? 'connected' : 'not_connected' };
          }
          if (integration.id === 2 && iotStatus.st) {
            return { ...integration, status: iotStatus.st.connected ? 'connected' : 'not_connected' };
          }
          if (integration.integrationType && status[integration.integrationType]) {
            return { ...integration, status: 'connected' };
          } else if (integration.integrationType) {
            return { ...integration, status: 'not_connected' };
          }
          return integration;
        }));
      } catch (error) {
        console.error('Error fetching integration status:', error);
      }
    };
    fetchStatus();
  }, []);

  const handleSync = async (integration) => {
    setSyncing(prev => ({ ...prev, [integration.id]: true }));
    try {
      let endpoint;
      if (integration.id === 1) {
        endpoint = '/api/iot/ha/sync';
      } else if (integration.id === 2) {
        endpoint = '/api/iot/st/sync';
      } else if (integration.name === 'Google Gmail') {
        endpoint = '/api/integrations/gmail/sync';
      } else if (integration.name === 'Google Calendar') {
        endpoint = '/api/integrations/calendar/sync';
      } else {
        return;
      }

      const response = await fetch(`${API_BASE_URL}${endpoint}`, { method: 'POST' });
      if (response.ok) {
        alert(`${integration.name} sync triggered successfully`);
      } else {
        alert(`Failed to sync ${integration.name}`);
      }
    } catch (error) {
      alert(`Error syncing ${integration.name}: ${error.message}`);
    } finally {
      setSyncing(prev => ({ ...prev, [integration.id]: false }));
    }
  };

  const handleConfigSave = async () => {
    try {
      let endpoint;
      if (configModal === 1) {
        endpoint = '/api/iot/ha/config';
      } else if (configModal === 2) {
        endpoint = '/api/iot/st/config';
      }

      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(configForm)
      });

      if (response.ok) {
        alert('Configuration saved successfully');
        setConfigModal(null);
        window.location.reload();
      } else {
        alert('Failed to save configuration');
      }
    } catch (error) {
      alert(`Error saving configuration: ${error.message}`);
    }
  };

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

      {configModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="glass p-6 rounded-2xl w-96">
            <h3 className="text-xl font-bold text-primary mb-4">
              {configModal === 1 ? 'Home Assistant' : 'SmartThings'} Configuration
            </h3>

            {configModal === 1 && (
              <>
                <div className="mb-4">
                  <label className="block text-text-secondary mb-2">HA URL</label>
                  <input
                    type="text"
                    className="w-full bg-card border border-border rounded-lg px-3 py-2 text-text-primary"
                    placeholder="http://192.168.1.x:8123"
                    onChange={(e) => setConfigForm({...configForm, ha_url: e.target.value})}
                  />
                </div>
                <div className="mb-4">
                  <label className="block text-text-secondary mb-2">Long-Lived Access Token</label>
                  <input
                    type="password"
                    className="w-full bg-card border border-border rounded-lg px-3 py-2 text-text-primary"
                    placeholder="Your HA token"
                    onChange={(e) => setConfigForm({...configForm, ha_token: e.target.value})}
                  />
                </div>
              </>
            )}

            {configModal === 2 && (
              <div className="mb-4">
                <label className="block text-text-secondary mb-2">Personal Access Token</label>
                <input
                  type="password"
                  className="w-full bg-card border border-border rounded-lg px-3 py-2 text-text-primary"
                  placeholder="Your SmartThings PAT"
                  onChange={(e) => setConfigForm({...configForm, st_pat: e.target.value})}
                />
              </div>
            )}

            <div className="flex gap-4">
              <button
                onClick={handleConfigSave}
                className="flex-1 py-2 bg-primary text-white rounded-lg hover:bg-primary/80"
              >
                Save
              </button>
              <button
                onClick={() => setConfigModal(null)}
                className="flex-1 py-2 bg-card text-text-secondary rounded-lg hover:bg-card-hover"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

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
              <div className="flex gap-2">
                {(integration.id === 1 || integration.id === 2) && (
                  <button
                    onClick={() => {
                      setConfigModal(integration.id);
                      setConfigForm({});
                    }}
                    className="px-4 py-2 bg-card/50 rounded-lg text-text-secondary hover:bg-card-hover/50 transition-colors"
                  >
                    Configure
                  </button>
                )}
                <button
                  onClick={() => (integration.status === 'connected') ? handleSync(integration) : null}
                  className="px-4 py-2 bg-card/50 rounded-lg text-text-secondary hover:bg-card-hover/50 transition-colors disabled:opacity-50"
                  disabled={syncing[integration.id] || integration.status !== 'connected'}
                >
                  {syncing[integration.id] ? 'Syncing...' : 'Sync'}
                </button>
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
};

export default Integrations;
