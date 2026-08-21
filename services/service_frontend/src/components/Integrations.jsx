import { motion } from 'framer-motion';
import { useState, useEffect, useCallback } from 'react';
import { CheckCircle, AlertTriangle, Settings, RefreshCw, X, Radar, Trash2 } from 'lucide-react';
import { API_BASE_URL } from '../config';

const integrationsList = [
  { id: 1, name: 'Home Assistant', integrationType: 'iot_ha', logo: '/assets/logos/homeassistant.svg', description: 'Local smart home control', configurable: true },
  { id: 2, name: 'SmartThings', integrationType: 'iot_st', logo: '/assets/logos/smartthings.svg', description: 'Cloud-based smart home control', configurable: true },
  { id: 3, name: 'Google', integrationType: 'google', logo: '/assets/logos/google.svg', description: 'Gmail + Calendar', configurable: false },
  { id: 4, name: 'OpenWeatherMap', integrationType: 'openweather', logo: '/assets/logos/openweathermap.svg', description: 'Weather & environment data', configurable: true },
  { id: 5, name: 'Spotify', integrationType: 'spotify', logo: '/assets/logos/spotify.svg', description: 'Music playback & recommendations', configurable: true },
  { id: 6, name: 'Alexa', integrationType: null, logo: '/assets/logos/alexa.svg', description: 'Amazon Echo compatibility', configurable: false },
  { id: 7, name: 'HomeKit', integrationType: null, logo: '/assets/logos/homekit.svg', description: 'Apple Home app integration', configurable: false },
  { id: 8, name: 'IFTTT', integrationType: null, logo: '/assets/logos/ifttt.svg', description: 'Applet automation', configurable: false },
  { id: 9, name: 'Google Maps', integrationType: null, logo: '/assets/logos/googlemaps.svg', description: 'Travel time and directions for events', configurable: false },
  { id: 10, name: 'Google Calendar', integrationType: 'google', logo: '/assets/logos/googlecalendar.svg', description: 'Upcoming events and scheduling', configurable: false },
  { id: 11, name: 'ESPHome', integrationType: 'iot_esphome', logo: '/assets/logos/esphome.svg', description: 'Local ESP device control (mDNS, no cloud)', configurable: true },
];

const ESPHOME_ID = 11;

const Integrations = () => {
  const [integrations, setIntegrations] = useState(integrationsList);
  const [syncing, setSyncing] = useState({});
  const [configModal, setConfigModal] = useState(null);
  const [configForm, setConfigForm] = useState({});
  const [espNodes, setEspNodes] = useState([]);
  const [espLoading, setEspLoading] = useState(false);
  const [espScanning, setEspScanning] = useState(false);
  const [espAcceptForm, setEspAcceptForm] = useState({});

  const fetchEspNodes = useCallback(async () => {
    setEspLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/iot/esphome/nodes`);
      if (response.ok) {
        setEspNodes(await response.json());
      }
    } catch (error) {
      console.error('Error fetching ESPHome nodes:', error);
    } finally {
      setEspLoading(false);
    }
  }, []);

  const handleEspDiscover = async () => {
    setEspScanning(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/iot/esphome/discover`, { method: 'POST' });
      if (!response.ok) alert('ESPHome discovery failed');
      await fetchEspNodes();
    } catch (error) {
      alert(`Error running ESPHome discovery: ${error.message}`);
    } finally {
      setEspScanning(false);
    }
  };

  const handleEspAccept = async (hostname) => {
    const form = espAcceptForm[hostname] || {};
    try {
      const response = await fetch(`${API_BASE_URL}/api/iot/esphome/nodes/${encodeURIComponent(hostname)}/accept`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ psk: form.psk || null, name: form.name || null }),
      });
      if (response.ok) {
        await fetchEspNodes();
      } else {
        const data = await response.json().catch(() => ({}));
        alert(`Failed to accept node: ${data.detail || response.statusText}`);
      }
    } catch (error) {
      alert(`Error accepting node: ${error.message}`);
    }
  };

  const handleEspRemove = async (hostname) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/iot/esphome/nodes/${encodeURIComponent(hostname)}`, {
        method: 'DELETE',
      });
      if (response.ok) {
        await fetchEspNodes();
      } else {
        alert('Failed to remove node');
      }
    } catch (error) {
      alert(`Error removing node: ${error.message}`);
    }
  };

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
          if (integration.id === ESPHOME_ID && iotStatus.esphome) {
            return { ...integration, status: iotStatus.esphome.connected ? 'connected' : 'not_connected' };
          }
          if (integration.integrationType === 'openweather') {
            return { ...integration, status: status.openweather ? 'connected' : 'not_connected' };
          }
          if (integration.integrationType === 'spotify') {
            const spotify = status.spotify || {};
            return { ...integration, status: spotify.authorized ? 'connected' : (spotify.configured ? 'requires_attention' : 'not_connected'), authUrl: spotify.auth_url || null };
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
      } else if (integration.id === ESPHOME_ID) {
        endpoint = '/api/iot/esphome/sync';
      } else if (integration.name === 'Google Gmail' || integration.name === 'Google') {
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
      let method = 'PUT';
      if (configModal === 1) {
        endpoint = '/api/iot/ha/config';
      } else if (configModal === 2) {
        endpoint = '/api/iot/st/config';
      } else if (configModal === 4) {
        endpoint = '/api/integrations/openweather/config';
      } else if (configModal === 5) {
        endpoint = '/api/music/spotify/auth';
        method = 'POST';
      } else {
        return;
      }

      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method,
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

  const handleSpotifyAuthorize = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/music/spotify/auth`);
      const data = await response.json();
      if (data.auth_url) {
        window.open(data.auth_url, '_blank', 'noopener,noreferrer');
      } else {
        alert('Save your Spotify credentials first, then authorize.');
      }
    } catch (error) {
      alert(`Error starting authorization: ${error.message}`);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'connected': return 'text-success border-success/40 bg-success/10';
      case 'requires_attention': return 'text-warning border-warning/40 bg-warning/10';
      case 'not_connected': return 'text-error border-error/40 bg-error/10';
      default: return 'text-text-tertiary border-border bg-border/10';
    }
  };

  const getStatusLabel = (status) => {
    switch (status) {
      case 'connected': return 'ACTIVE';
      case 'requires_attention': return 'ATTENTION';
      case 'not_connected': return 'NOT CONFIGURED';
      default: return 'UNKNOWN';
    }
  };

  const openConfig = (integration) => {
    setConfigModal(integration.id);
    setConfigForm({});
    if (integration.id === ESPHOME_ID) {
      fetchEspNodes();
    }
  };

  return (
    <div>
      <h2 className="text-2xl font-bold text-primary mb-6 drop-shadow-lg">Third-Party Integrations</h2>

      {configModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setConfigModal(null)}>
          <div className={`glass p-6 rounded-2xl ${configModal === ESPHOME_ID ? 'w-[32rem] max-h-[80vh] overflow-y-auto' : 'w-96'}`} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-bold text-primary">
                {integrations.find(i => i.id === configModal)?.name} Configuration
              </h3>
              <button onClick={() => setConfigModal(null)} className="text-text-secondary hover:text-text-primary">
                <X className="w-5 h-5" />
              </button>
            </div>

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

            {configModal === 4 && (
              <div className="mb-4">
                <label className="block text-text-secondary mb-2">OpenWeatherMap API Key</label>
                <input
                  type="password"
                  className="w-full bg-card border border-border rounded-lg px-3 py-2 text-text-primary"
                  placeholder="Your OWM API key"
                  onChange={(e) => setConfigForm({...configForm, api_key: e.target.value})}
                />
                <p className="text-xs text-text-tertiary mt-2">Get a key at openweathermap.org — powers the weather & environment panel.</p>
              </div>
            )}

            {configModal === 5 && (
              <>
                <div className="mb-4">
                  <label className="block text-text-secondary mb-2">Client ID</label>
                  <input
                    type="text"
                    className="w-full bg-card border border-border rounded-lg px-3 py-2 text-text-primary"
                    placeholder="Spotify Client ID"
                    onChange={(e) => setConfigForm({...configForm, client_id: e.target.value})}
                  />
                </div>
                <div className="mb-4">
                  <label className="block text-text-secondary mb-2">Client Secret</label>
                  <input
                    type="password"
                    className="w-full bg-card border border-border rounded-lg px-3 py-2 text-text-primary"
                    placeholder="Spotify Client Secret"
                    onChange={(e) => setConfigForm({...configForm, client_secret: e.target.value})}
                  />
                </div>
                <div className="mb-4">
                  <label className="block text-text-secondary mb-2">Redirect URI</label>
                  <input
                    type="text"
                    className="w-full bg-card border border-border rounded-lg px-3 py-2 text-text-primary"
                    placeholder={`${window.location.origin}/api/music/spotify/callback`}
                    onChange={(e) => setConfigForm({...configForm, redirect_uri: e.target.value})}
                  />
                  <p className="text-xs text-text-tertiary mt-2">
                    Create an app at developer.spotify.com and add this URI to its Redirect URIs.
                  </p>
                </div>
                <div className="mb-4">
                  <button
                    onClick={handleSpotifyAuthorize}
                    className="w-full py-2 bg-primary text-white rounded-lg hover:bg-primary/80"
                  >
                    Authorize on Spotify
                  </button>
                  <p className="text-xs text-text-tertiary mt-2">Opens Spotify&apos;s login page in a new tab, then returns here.</p>
                </div>
              </>
            )}

            {configModal === ESPHOME_ID && (
              <div className="mb-4">
                <p className="text-xs text-text-tertiary mb-4">
                  ESPHome nodes are discovered locally over mDNS — no cloud account or URL/token to enter.
                  Newly discovered nodes need to be explicitly accepted before ALFR3D connects to them
                  (a node broadcasting on your LAN isn&apos;t necessarily one you intended to onboard).
                  PSK is optional and only needed if the node has Noise-protocol encryption enabled.
                </p>

                <button
                  onClick={handleEspDiscover}
                  disabled={espScanning}
                  className="w-full flex items-center justify-center gap-2 py-2 mb-4 bg-primary text-white rounded-lg hover:bg-primary/80 disabled:opacity-50"
                >
                  <Radar className={`w-4 h-4 ${espScanning ? 'animate-spin' : ''}`} />
                  {espScanning ? 'Scanning (~8s)...' : 'Scan for ESPHome devices'}
                </button>

                {espLoading && <p className="text-sm text-text-tertiary">Loading nodes...</p>}

                {!espLoading && espNodes.filter(n => !n.accepted).length > 0 && (
                  <div className="mb-4">
                    <h4 className="text-sm font-semibold text-text-secondary mb-2">Discovered (not yet accepted)</h4>
                    {espNodes.filter(n => !n.accepted).map((node) => (
                      <div key={node.hostname} className="bg-card/50 rounded-lg p-3 mb-2">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm text-text-primary font-mono">{node.name || node.hostname}</span>
                          <span className="text-xs text-text-tertiary">{node.ip_address}</span>
                        </div>
                        <input
                          type="password"
                          placeholder="PSK (optional)"
                          className="w-full bg-card border border-border rounded-lg px-2 py-1 text-xs text-text-primary mb-2"
                          onChange={(e) => setEspAcceptForm({
                            ...espAcceptForm,
                            [node.hostname]: { ...espAcceptForm[node.hostname], psk: e.target.value },
                          })}
                        />
                        <button
                          onClick={() => handleEspAccept(node.hostname)}
                          className="w-full py-1.5 bg-success/20 text-success rounded-lg text-xs hover:bg-success/30"
                        >
                          Accept
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {!espLoading && espNodes.filter(n => n.accepted).length > 0 && (
                  <div className="mb-2">
                    <h4 className="text-sm font-semibold text-text-secondary mb-2">Accepted</h4>
                    {espNodes.filter(n => n.accepted).map((node) => (
                      <div key={node.hostname} className="flex items-center justify-between bg-card/50 rounded-lg p-3 mb-2">
                        <div>
                          <span className="text-sm text-text-primary font-mono block">{node.name || node.hostname}</span>
                          <span className="text-xs text-text-tertiary">{node.ip_address}</span>
                        </div>
                        <button
                          onClick={() => handleEspRemove(node.hostname)}
                          className="p-1.5 text-error hover:bg-error/10 rounded-lg"
                          title="Remove node"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {!espLoading && espNodes.length === 0 && (
                  <p className="text-sm text-text-tertiary">No nodes yet — run a scan to discover ESPHome devices on the LAN.</p>
                )}
              </div>
            )}

            <div className="flex gap-4">
              {configModal !== ESPHOME_ID && (
                <button
                  onClick={handleConfigSave}
                  className="flex-1 py-2 bg-primary text-white rounded-lg hover:bg-primary/80"
                >
                  Save
                </button>
              )}
              <button
                onClick={() => setConfigModal(null)}
                className="flex-1 py-2 bg-card text-text-secondary rounded-lg hover:bg-card-hover"
              >
                {configModal === ESPHOME_ID ? 'Close' : 'Cancel'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-6">
        {integrations.map((integration, index) => (
          <motion.div
            key={integration.id}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: index * 0.05, duration: 0.4 }}
            whileHover={{ scale: 1.02 }}
            onClick={() => openConfig(integration)}
            className="glass rounded-2xl p-5 cursor-pointer"
          >
            <div className="flex items-start justify-between mb-3">
              <div className="w-14 h-14 rounded-xl bg-white/5 flex items-center justify-center overflow-hidden p-1.5">
                <img src={integration.logo} alt={integration.name} className="w-full h-full object-contain" />
              </div>
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-mono tracking-wider ${getStatusColor(integration.status)}`}>
                {integration.status === 'connected' && <CheckCircle className="w-3 h-3" />}
                {integration.status === 'requires_attention' && <AlertTriangle className="w-3 h-3" />}
                {integration.status === 'not_connected' && <Settings className="w-3 h-3" />}
                {getStatusLabel(integration.status)}
              </span>
            </div>

            <h3 className="text-base font-semibold text-text-primary mb-1">{integration.name}</h3>
            <p className="text-xs text-text-tertiary mb-3">{integration.description}</p>

            <div className="flex items-center gap-2">
              {integration.configurable && (
                <button
                  onClick={(e) => { e.stopPropagation(); openConfig(integration); }}
                  className="flex items-center gap-1 px-3 py-1.5 bg-card/50 rounded-lg text-xs text-text-secondary hover:bg-card-hover/50 hover:text-primary transition-colors"
                >
                  <Settings className="w-3.5 h-3.5" /> Configure
                </button>
              )}
              {integration.id === 1 || integration.id === 2 || integration.id === ESPHOME_ID || integration.integrationType === 'google' ? (
                <button
                  onClick={(e) => { e.stopPropagation(); if (integration.status === 'connected') handleSync(integration); }}
                  className="flex items-center gap-1 px-3 py-1.5 bg-card/50 rounded-lg text-xs text-text-secondary hover:bg-card-hover/50 hover:text-primary transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  disabled={syncing[integration.id] || integration.status !== 'connected'}
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${syncing[integration.id] ? 'animate-spin' : ''}`} />
                  {syncing[integration.id] ? 'Syncing' : 'Sync'}
                </button>
              ) : null}
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
};

export default Integrations;
