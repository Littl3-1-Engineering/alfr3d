import { motion } from 'framer-motion';
import { useState, useEffect, useRef } from 'react';
import PropTypes from 'prop-types';
import { Terminal, ChevronRight, Network, Database, FileCode2, RefreshCw, Download, Save, Power, Server } from 'lucide-react';
import { API_BASE_URL } from '../config';
import { apiFetch } from '../utils/apiClient';
import { useAuth } from '../utils/useAuth';
import socket from '../utils/socket';

const Section = ({ icon: Icon, title, children, defaultOpen = false }) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="glass rounded-2xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-fui-dim/40 transition-colors"
      >
        <span className="flex items-center gap-3 text-text-primary font-medium">
          <Icon className="w-5 h-5 text-fui-accent" />
          {title}
        </span>
        <ChevronRight className={`w-4 h-4 text-fui-text/60 transition-transform ${open ? 'rotate-90' : ''}`} />
      </button>
      {open && <div className="px-5 pb-5">{children}</div>}
    </div>
  );
};

Section.propTypes = {
  icon: PropTypes.elementType.isRequired,
  title: PropTypes.string.isRequired,
  children: PropTypes.node,
  defaultOpen: PropTypes.bool,
};

const System = () => {
  const { isAuthenticated } = useAuth();
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const logEndRef = useRef(null);
  const [enabledTags, setEnabledTags] = useState(() => new Set(['SYS', 'INIT', 'SCAN', 'UPD', 'EVT', 'ERR']));
  const logIdRef = useRef(0);

  const [network, setNetwork] = useState(null);
  const [database, setDatabase] = useState(null);
  const [dbBackingUp, setDbBackingUp] = useState(false);
  const [config, setConfig] = useState(null);
  const [configDirty, setConfigDirty] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const [services, setServices] = useState([]);
  const [restarting, setRestarting] = useState({});

  const addLog = (tag, message, type = 'info') => {
    const ts = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    logIdRef.current += 1;
    return { id: logIdRef.current, ts, tag, message, type };
  };

  const fetchNetwork = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/system/network`);
      if (res.ok) setNetwork(await res.json());
    } catch (e) { console.error('network fetch failed', e); }
  };

  const fetchDatabase = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/system/database`);
      if (res.ok) setDatabase(await res.json());
    } catch (e) { console.error('database fetch failed', e); }
  };

  const fetchConfig = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/system/config`);
      if (res.ok) {
        const data = await res.json();
        setConfig(data.content);
      }
    } catch (e) { console.error('config fetch failed', e); }
  };

  const fetchServices = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/system/services`);
      if (res.ok) setServices(await res.json());
    } catch (e) { console.error('services fetch failed', e); }
  };

  const handleBackup = async () => {
    setDbBackingUp(true);
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/system/database/backup`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        alert(`Backup completed: ${(data.databases || []).join(', ')}`);
      } else {
        alert('Backup failed');
      }
    } catch (e) {
      alert(`Backup error: ${e.message}`);
    } finally {
      setDbBackingUp(false);
    }
  };

  const handleConfigSave = async () => {
    setConfigSaving(true);
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/system/config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: config }),
      });
      if (res.ok) {
        alert('Config saved');
        setConfigDirty(false);
      } else {
        const err = await res.json().catch(() => ({}));
        alert(`Save failed: ${err.detail || 'invalid JSON'}`);
      }
    } catch (e) {
      alert(`Save error: ${e.message}`);
    } finally {
      setConfigSaving(false);
    }
  };

  const handleRestart = async (name) => {
    if (!window.confirm(`Restart ${name}?`)) return;
    setRestarting(prev => ({ ...prev, [name]: true }));
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/system/services/${encodeURIComponent(name)}/restart`, { method: 'POST' });
      if (res.ok) {
        alert(`Restart triggered: ${name}`);
        setTimeout(fetchServices, 4000);
      } else {
        alert(`Restart failed: ${name}`);
      }
    } catch (e) {
      alert(`Restart error: ${e.message}`);
    } finally {
      setRestarting(prev => ({ ...prev, [name]: false }));
    }
  };

  useEffect(() => {
    fetchNetwork();
    fetchDatabase();
    fetchConfig();
    fetchServices();

    const init = async () => {
      const initial = [];

      initial.push(addLog('SYS', 'Initializing system monitor...'));

      try {
        const [containersRes, eventsRes, iotRes, integrationsRes] = await Promise.allSettled([
          fetch(`${API_BASE_URL}/api/containers`),
          fetch(`${API_BASE_URL}/api/events`),
          fetch(`${API_BASE_URL}/api/iot/status`),
          fetch(`${API_BASE_URL}/api/integrations/status`),
        ]);

        if (containersRes.status === 'fulfilled' && containersRes.value.ok) {
          const containers = await containersRes.value.json();
          initial.push(addLog('INIT', `${containers.length} containers detected`));
          containers.forEach(c => {
            const status = c.errors > 0 ? 'ERR' : 'OK';
            initial.push(addLog('SCAN', `${c.name}: CPU ${c.cpu}% MEM ${c.mem}% DSK ${c.disk}% [${status}]`));
          });
        } else {
          initial.push(addLog('ERR', 'Failed to fetch container data'));
          setError(true);
        }

        if (eventsRes.status === 'fulfilled' && eventsRes.value.ok) {
          const events = await eventsRes.value.json();
          const recent = events.slice(-5).reverse();
          if (recent.length > 0) {
            initial.push(addLog('INIT', `Loading ${recent.length} recent events`));
            recent.forEach(e => {
              initial.push(addLog('EVT', e.message || JSON.stringify(e)));
            });
          } else {
            initial.push(addLog('INIT', 'No recent events'));
          }
        }

        if (iotRes.status === 'fulfilled' && iotRes.value.ok) {
          const iot = await iotRes.value.json();
          initial.push(addLog('INIT', `Home Assistant: ${iot.ha?.connected ? 'CONNECTED' : 'OFFLINE'}`));
          initial.push(addLog('INIT', `SmartThings: ${iot.st?.connected ? 'CONNECTED' : 'OFFLINE'}`));
        }

        if (integrationsRes.status === 'fulfilled' && integrationsRes.value.ok) {
          const intg = await integrationsRes.value.json();
          initial.push(addLog('INIT', `Google integration: ${intg.google ? 'CONNECTED' : 'OFFLINE'}`));
        }

        initial.push(addLog('SYS', 'System monitor online'));
      } catch (e) {
        initial.push(addLog('ERR', `Initialization error: ${e.message}`));
        setError(true);
      }

      setLogs(initial);
      setLoading(false);
    };

    init();
  }, []);

  useEffect(() => {
    const handleContainers = (containers) => {
      setLogs(prev => {
        const newLogs = containers.map(c => {
          const status = c.errors > 0 ? 'ERR' : 'OK';
          return addLog('UPD', `${c.name}: CPU ${c.cpu}% MEM ${c.mem}% DSK ${c.disk}% [${status}]`);
        });
        return [...prev, ...newLogs];
      });
    };

    const handleEvents = (events) => {
      setLogs(prev => {
        const latest = Array.isArray(events) ? events : [events];
        const newLogs = latest.slice(-3).map(e =>
          addLog('EVT', e.message || JSON.stringify(e))
        );
        return [...prev, ...newLogs];
      });
    };

    socket.on('containers', handleContainers);
    socket.on('events', handleEvents);

    return () => {
      socket.off('containers', handleContainers);
      socket.off('events', handleEvents);
    };
  }, []);

  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  const getTagColor = (tag) => {
    switch (tag) {
      case 'ERR': return 'text-red-400';
      case 'EVT': return 'text-blue-400';
      case 'UPD': return 'text-amber-400';
      case 'SCAN': return 'text-fui-text';
      case 'INIT': return 'text-cyan-400';
      default: return 'text-success';
    }
  };

  const toggleTag = (tag) => {
    setEnabledTags(prev => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag); else next.add(tag);
      return next;
    });
  };

  const filteredLogs = logs.filter(log => enabledTags.has(log.tag));

  const InfoRow = ({ label, value }) => (
    <div className="flex justify-between items-center py-1.5 border-b border-border/20 last:border-0">
      <span className="font-mono text-xs text-fui-text/60 uppercase tracking-wider">{label}</span>
      <span className="font-mono text-xs text-fui-text">{value || 'N/A'}</span>
    </div>
  );

  InfoRow.propTypes = {
    label: PropTypes.string.isRequired,
    value: PropTypes.string,
  };

  return (
    <div>
      <h2 className="text-2xl font-bold text-primary mb-6 drop-shadow-lg">System Monitor</h2>

      <div className="space-y-4 mb-8">
        <Section icon={Network} title="Network">
          {network ? (
            <div>
              <InfoRow label="Hostname" value={network.hostname} />
              <InfoRow label="IP Address" value={network.ip} />
              <InfoRow label="DNS" value={network.dns} />
              <InfoRow label="Gateway" value={network.gateway} />
            </div>
          ) : (
            <p className="text-fui-text/60 font-mono text-xs">LOADING NETWORK INFO...</p>
          )}
        </Section>

        <Section icon={Database} title="Database">
          {database ? (
            <div>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${database.connected ? 'bg-success' : 'bg-error'}`} />
                  <span className="font-mono text-xs text-fui-text uppercase tracking-wider">
                    {database.connected ? `Connected — MySQL ${database.version}` : 'Disconnected'}
                  </span>
                </div>
                <button
                  onClick={handleBackup}
                  disabled={dbBackingUp || !database.connected || !isAuthenticated}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-card/50 rounded-lg text-xs text-fui-text hover:bg-card-hover/50 hover:text-primary transition-colors disabled:opacity-50"
                >
                  <Download className={`w-3.5 h-3.5 ${dbBackingUp ? 'animate-pulse' : ''}`} />
                  {dbBackingUp ? 'Backing up...' : 'Backup'}
                </button>
              </div>
              {database.connected && (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                  {database.tables.map((t) => (
                    <div key={t.name} className="flex justify-between items-center px-2 py-1.5 bg-fui-dim/40 border border-border/20 rounded">
                      <span className="font-mono text-[10px] text-fui-text truncate mr-2">{t.name}</span>
                      <span className="font-mono text-[10px] text-fui-accent">{t.rows}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p className="text-fui-text/60 font-mono text-xs">LOADING DATABASE INFO...</p>
          )}
        </Section>

        <Section icon={FileCode2} title="Config Editor" defaultOpen={false}>
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="font-mono text-xs text-fui-text/60 uppercase tracking-wider">
                {config ? `${config.length} chars` : 'LOADING...'}
              </span>
              <button
                onClick={handleConfigSave}
                disabled={!configDirty || configSaving || !isAuthenticated}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-primary/20 border border-primary rounded-lg text-xs text-primary hover:bg-primary/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Save className="w-3.5 h-3.5" />
                {configSaving ? 'Saving...' : 'Save'}
              </button>
            </div>
            <textarea
              value={config || ''}
              onChange={(e) => { setConfig(e.target.value); setConfigDirty(true); }}
              spellCheck={false}
              className="w-full h-64 bg-black/50 border border-border rounded-lg p-3 font-mono text-xs text-success focus:outline-none focus:border-primary"
              placeholder="{}"
            />
            <p className="text-[10px] font-mono text-fui-text/40 mt-1 uppercase tracking-wider">Path: /etc/alfr3d/config.json</p>
          </div>
        </Section>

        <Section icon={Server} title="Service Control">
          <div className="space-y-2">
            {services.length === 0 && <p className="text-fui-text/60 font-mono text-xs">NO SERVICES DETECTED</p>}
            {services.map(service => (
              <div key={service.name} className="flex items-center justify-between px-3 py-2 bg-fui-dim/40 border border-border/20 rounded">
                <div className="flex items-center gap-2 min-w-0">
                  <span className={`w-2 h-2 rounded-full flex-shrink-0 ${service.status === 'running' ? 'bg-success' : 'bg-error'}`} />
                  <span className="font-mono text-xs text-fui-text truncate">{service.name}</span>
                </div>
                <button
                  onClick={() => handleRestart(service.name)}
                  disabled={restarting[service.name] || !isAuthenticated}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-card/50 rounded-lg text-xs text-fui-text hover:bg-card-hover/50 hover:text-primary transition-colors disabled:opacity-50 ml-2"
                >
                  <Power className={`w-3.5 h-3.5 ${restarting[service.name] ? 'animate-spin' : ''}`} />
                  {restarting[service.name] ? 'Restarting' : 'Restart'}
                </button>
              </div>
            ))}
            {services.length > 0 && (
              <button
                onClick={fetchServices}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-card/50 rounded-lg text-xs text-fui-text/60 hover:text-primary transition-colors"
              >
                <RefreshCw className="w-3.5 h-3.5" /> Refresh
              </button>
            )}
          </div>
        </Section>
      </div>

      <div className="glass rounded-2xl p-6 font-mono text-sm">
        <div className="flex items-center space-x-2 mb-4">
          <Terminal className="w-5 h-5 text-primary" />
          <span className="text-primary">ALFR3D Terminal</span>
          <span className="text-fui-text/40 text-xs ml-auto">{filteredLogs.length}/{logs.length} entries</span>
        </div>

        <div className="flex flex-wrap gap-x-4 gap-y-1 mb-3 px-1">
          {['SYS', 'INIT', 'SCAN', 'UPD', 'EVT', 'ERR'].map(tag => (
            <label key={tag} className="flex items-center gap-2 cursor-pointer select-none">
              <span className={`text-xs font-bold ${getTagColor(tag)}`}>[{tag}]</span>
              <button
                type="button"
                role="switch"
                aria-checked={enabledTags.has(tag)}
                onClick={() => toggleTag(tag)}
                className={`relative w-8 h-4 rounded-full transition-colors ${
                  enabledTags.has(tag) ? 'bg-primary' : 'bg-gray-600'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white transition-transform ${
                    enabledTags.has(tag) ? 'translate-x-4' : 'translate-x-0'
                  }`}
                />
              </button>
            </label>
          ))}
        </div>

        <div className="bg-black/50 rounded-lg p-4 h-96 overflow-y-auto">
          {loading && logs.length === 0 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center space-x-2 mb-1"
            >
              <ChevronRight className="w-3 h-3 text-primary flex-shrink-0" />
              <span className="text-amber-400">[WAITING FOR DATA...]</span>
            </motion.div>
          )}

          {filteredLogs.map((log) => (
            <motion.div
              key={log.id}
              initial={{ opacity: 0, x: -5 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.2 }}
              className="flex items-start space-x-2 mb-1"
            >
              <ChevronRight className="w-3 h-3 text-primary flex-shrink-0 mt-0.5" />
              <span className="text-fui-text/40 flex-shrink-0">[{log.ts}]</span>
              <span className={`flex-shrink-0 font-bold ${getTagColor(log.tag)}`}>[{log.tag}]</span>
              <span className="text-success break-all">{log.message}</span>
            </motion.div>
          ))}

          {error && logs.length > 0 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center space-x-2 mb-1 mt-2"
            >
              <ChevronRight className="w-3 h-3 text-red-400 flex-shrink-0" />
              <span className="text-red-400">[WARN] Some data sources unavailable</span>
            </motion.div>
          )}

          <div ref={logEndRef} />
        </div>

        <div className="mt-4 flex items-center space-x-2">
          <span className="text-primary">alfr3d@matrix:~$</span>
          <span className="animate-pulse">_</span>
        </div>
      </div>
    </div>
  );
};

export default System;
