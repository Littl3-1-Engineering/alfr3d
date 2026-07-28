import { motion } from 'framer-motion';
import { useState, useEffect, useRef } from 'react';
import { Terminal, ChevronRight } from 'lucide-react';
import { API_BASE_URL } from '../config';
import socket from '../utils/socket';

const System = () => {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const logEndRef = useRef(null);
  const logIdRef = useRef(0);

  const addLog = (tag, message, type = 'info') => {
    const ts = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    logIdRef.current += 1;
    return { id: logIdRef.current, ts, tag, message, type };
  };

  useEffect(() => {
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

  return (
    <div>
      <h2 className="text-2xl font-bold text-primary mb-6 drop-shadow-lg">System Monitor</h2>

      <div className="glass rounded-2xl p-6 font-mono text-sm">
        <div className="flex items-center space-x-2 mb-4">
          <Terminal className="w-5 h-5 text-primary" />
          <span className="text-primary">ALFR3D Terminal</span>
          <span className="text-fui-text/40 text-xs ml-auto">{logs.length} entries</span>
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

          {logs.map((log) => (
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
