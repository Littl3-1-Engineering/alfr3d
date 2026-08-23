import { useState, useEffect, useRef, useCallback, useMemo, memo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Lightbulb, Thermometer, Wifi, ZoomIn, ZoomOut, ChevronDown, ChevronUp, X, Droplets, Activity, Gauge, Camera, ImagePlus, Trash2, Search, List, Map } from 'lucide-react';
import PropTypes from 'prop-types';
import BlueprintSVG from './cassiopeia_blueprint.svg?react';
import ControlBlade from './ControlBlade';
import { API_BASE_URL } from '../config';
import { apiFetch } from '../utils/apiClient';
import { getGravatarUrl } from '../utils/gravatarUtils';
import socket from '../utils/socket';

const FLOORPLAN_KEY = 'alfr3d-floorplan';

const deviceCategory = (device) => {
  const type = (device.type === 'iot' && device.local_device?.device_type
    ? device.local_device.device_type
    : device.deviceType || device.type)?.toLowerCase();
  if (type === 'light' || type === 'switch') return 'LIGHTING';
  if (type === 'climate' || type === 'thermostat') return 'CLIMATE';
  if (type === 'sensor' || type === 'binary_sensor') return 'SENSORS';
  if (type === 'camera') return 'CAMERAS';
  if (type === 'cover') return 'COVERS';
  return 'OTHER';
};

const DeviceIcon = memo(({ device, onRemove }) => {
  const Icon = useMemo(() => {
    const deviceType = device.type === 'iot' && device.local_device?.device_type
      ? device.local_device.device_type
      : device.deviceType;

    const type = deviceType?.toLowerCase();

    if (type === 'light' || deviceType === 4) return Lightbulb;
    if (type === 'climate' || type === 'thermostat') return Thermometer;
    if (type === 'sensor') return Droplets;
    if (type === 'binary_sensor') return Activity;
    if (type === 'camera') return Camera;
    if (type === 'cover') return Gauge;
    if (type === 'switch' || type === 'fan' || type === 'lock' || type === 'media_player') return Wifi;

    return Wifi;
  }, [device.type, device.deviceType, device.local_device]);

  return (
    <div className="relative">
      <Icon className={`w-8 h-8 ${device.state === 'online' ? 'text-primary' : 'text-text-tertiary'}`} />
      <button
        onClick={(e) => { e.stopPropagation(); onRemove(device.id); }}
        className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full flex items-center justify-center text-white text-xs"
      >
        <X className="w-2 h-2" />
      </button>
    </div>
  );
});

DeviceIcon.displayName = 'DeviceIcon';

DeviceIcon.propTypes = {
  device: PropTypes.object.isRequired,
  onRemove: PropTypes.func.isRequired,
};

const DeviceListItem = memo(({ device, onDragEnd, onClick, onDeviceSelect }) => {
  const Icon = useMemo(() => {
    if (device.type === 'iot') {
      switch (device.deviceType) {
        case 'light': return Lightbulb;
        case 'climate':
        case 'thermostat': return Thermometer;
        default: return Wifi;
      }
    }
    switch (device.deviceType) {
      case 'light': return Lightbulb;
      case 'thermostat': return Thermometer;
      default: return Wifi;
    }
  }, [device.type, device.deviceType]);

  return (
    <motion.div
      drag
      dragConstraints={{ left: 0, top: 0, right: 0, bottom: 0 }}
      onDragEnd={(event, info) => onDragEnd(device, event, info)}
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 0, duration: 0.3 }}
      className="flex items-center p-2 bg-card/50 rounded-lg cursor-pointer hover:bg-card-hover/50"
      onClick={() => { onClick(device); onDeviceSelect && onDeviceSelect(device); }}
    >
      <div className="relative">
        <Icon className={`w-6 h-6 mr-3 ${device.state === 'online' ? 'text-primary' : 'text-text-tertiary'}`} />
      </div>
      <div>
        <div className="text-sm font-medium text-text-inverse">{device.name}</div>
        <div className="text-xs text-text-tertiary">{device.type === 'iot' ? device.source : device.type} - {device.state}</div>
      </div>
    </motion.div>
  );
});

DeviceListItem.displayName = 'DeviceListItem';

DeviceListItem.propTypes = {
  device: PropTypes.object.isRequired,
  onDragEnd: PropTypes.func.isRequired,
  onClick: PropTypes.func.isRequired,
  onDeviceSelect: PropTypes.func,
};

const mergeWithIot = (alfredDevs, iotDevs) => [
  ...alfredDevs.map(d => ({ ...d, type: 'local' })),
  ...iotDevs
    .filter(iot => iot.linked)
    .map(iot => ({
      id: `iot_${iot.id}`,
      name: iot.name,
      deviceType: iot.device_type,
      user: 'iot',
      type: 'iot',
      source: iot.source,
      entity_id: iot.ha_entity_id || iot.st_device_id,
      state: iot.online ? 'online' : 'offline',
      position: iot.local_device && iot.local_device.position_x != null
        ? { x: iot.local_device.position_x, y: iot.local_device.position_y }
        : null,
      mac_address: iot.mac_address,
      linked: !!iot.local_device,
    })),
];

const Blueprint = ({ onDeviceSelect }) => {
  const [devices, setDevices] = useState([]);
  const [users, setUsers] = useState([]);
  const [zoom, setZoom] = useState(1);
  const [isListExpanded, setIsListExpanded] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [view, setView] = useState('map');
  const [search, setSearch] = useState('');
  const [floorplan, setFloorplan] = useState(null);
  const blueprintRef = useRef(null);
  const alfredRef = useRef([]);
  const iotRef = useRef([]);

  useEffect(() => {
    setFloorplan(localStorage.getItem(FLOORPLAN_KEY));
  }, []);

  const fetchDevices = useCallback(async () => {
    try {
      const response = await fetch(API_BASE_URL + '/api/devices');
      const allDevices = await response.json();
      const alfredDevices = allDevices.filter(device => device.user === 'alfr3d');
      alfredRef.current = alfredDevices;

      let iotDevices = [];
      try {
        const iotResponse = await fetch(API_BASE_URL + '/api/iot/devices');
        if (iotResponse.ok) {
          iotDevices = await iotResponse.json();
          iotRef.current = iotDevices;
        }
      } catch (iotError) {
        console.error('Error fetching IoT devices:', iotError);
      }

      setDevices(mergeWithIot(alfredDevices, iotDevices));
    } catch (error) {
      console.error('Error fetching devices:', error);
    }
  }, []);

  const fetchUsers = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/users?online=true`);
      if (response.ok) {
        const data = await response.json();
        setUsers(data);
      }
    } catch (error) {
      console.error('Error fetching users:', error);
    }
  }, []);

  useEffect(() => {
    fetchDevices();
    fetchUsers();

    socket.on('devices', (allDevices) => {
      const alfredDevices = allDevices.filter(device => device.user === 'alfr3d');
      alfredRef.current = alfredDevices;
      setDevices(mergeWithIot(alfredDevices, iotRef.current));
    });

    socket.on('iot_devices', (iotDevices) => {
      iotRef.current = iotDevices;
      setDevices(mergeWithIot(alfredRef.current, iotDevices));
    });

    socket.on('users', setUsers);

    return () => {
      socket.off('devices');
      socket.off('iot_devices');
      socket.off('users');
    };
  }, [fetchDevices, fetchUsers]);

  const positionedDevices = useMemo(() => devices.filter(d => d.position), [devices]);
  const unpositionedDevices = useMemo(() => devices.filter(d => !d.position), [devices]);

  // Online users placed at the position of their linked device (device.user matches username).
  const locatedUsers = useMemo(() => {
    if (!Array.isArray(users)) return [];
    return users
      .filter(u => u.state === 'online')
      .map(u => {
        const linkedDevice = positionedDevices.find(d => d.user === u.name);
        return linkedDevice ? { user: u, position: linkedDevice.position } : null;
      })
      .filter(Boolean);
  }, [users, positionedDevices]);

  const handleZoomIn = useCallback(() => setZoom(prev => Math.min(prev + 0.2, 3)), []);
  const handleZoomOut = useCallback(() => setZoom(prev => Math.max(prev - 0.2, 0.5)), []);

  const handleFloorplanUpload = useCallback((e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result;
      localStorage.setItem(FLOORPLAN_KEY, dataUrl);
      setFloorplan(dataUrl);
    };
    reader.readAsDataURL(file);
  }, []);

  const handleFloorplanReset = useCallback(() => {
    localStorage.removeItem(FLOORPLAN_KEY);
    setFloorplan(null);
  }, []);

  const updateDevicePosition = useCallback(async (deviceId, position) => {
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/devices/${deviceId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ position }),
      });
      if (response.ok) {
        setDevices(prev => prev.map(d => d.id === deviceId ? { ...d, position } : d));
      } else {
        console.error('Failed to update device position');
      }
    } catch (error) {
      console.error('Error updating device position:', error);
    }
  }, []);

  const handleDragEnd = useCallback((device, event, info) => {
    if (!blueprintRef.current) return;
    const rect = blueprintRef.current.getBoundingClientRect();
    const x = (info.point.x - rect.left) / zoom;
    const y = (info.point.y - rect.top) / zoom;

    if (device.type === 'iot' && device.linked && device.local_device?.id) {
      updateDevicePosition(device.local_device.id, { x, y });
    } else if (device.type !== 'iot') {
      updateDevicePosition(device.id, { x, y });
    }
  }, [zoom, updateDevicePosition]);

  const removeDeviceFromBlueprint = useCallback((deviceId) => {
    updateDevicePosition(deviceId, null);
  }, [updateDevicePosition]);

  const handleDeviceSelect = useCallback((device) => {
    setSelectedDevice(device);
  }, []);

  const handleDeviceClick = useCallback((device) => {
    setSelectedDevice(device);
    onDeviceSelect && onDeviceSelect(device);
  }, [onDeviceSelect]);

  const filteredDevices = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return devices;
    return devices.filter(d => (d.name || '').toLowerCase().includes(q) || (d.deviceType || '').toLowerCase().includes(q));
  }, [devices, search]);

  const groupedByCategory = useMemo(() => {
    const groups = {};
    for (const device of filteredDevices) {
      const cat = deviceCategory(device);
      (groups[cat] = groups[cat] || []).push(device);
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [filteredDevices]);

  const initialsOf = (name) => (name || '?').split(/[\s._-]+/).filter(Boolean).slice(0, 2).map(p => p[0].toUpperCase()).join('');

  return (
    <div className="glass rounded-2xl p-6 h-[800px] relative overflow-auto">
      <div className="flex flex-wrap justify-between items-center gap-3 mb-4">
        <h2 className="text-xl font-bold text-primary drop-shadow-lg">Home Blueprint</h2>

        <div className="flex items-center gap-2">
          {/* View toggle */}
          <div className="bg-card/50 rounded-lg p-1 flex">
            <button
              onClick={() => setView('map')}
              className={`px-3 py-1 rounded text-xs font-mono flex items-center gap-1 transition-colors ${
                view === 'map' ? 'bg-primary text-text-inverse' : 'text-text-secondary hover:text-primary'
              }`}
            >
              <Map className="w-3.5 h-3.5" /> BLUEPRINT
            </button>
            <button
              onClick={() => setView('list')}
              className={`px-3 py-1 rounded text-xs font-mono flex items-center gap-1 transition-colors ${
                view === 'list' ? 'bg-primary text-text-inverse' : 'text-text-secondary hover:text-primary'
              }`}
            >
              <List className="w-3.5 h-3.5" /> LIST
            </button>
          </div>

          {/* Floorplan controls */}
          <label className="p-2 bg-card/50 rounded-lg hover:bg-card-hover/50 cursor-pointer" title="Upload floorplan image">
            <ImagePlus className="w-5 h-5 text-primary" />
            <input type="file" accept="image/*" className="hidden" onChange={handleFloorplanUpload} />
          </label>
          {floorplan && (
            <button onClick={handleFloorplanReset} className="p-2 bg-card/50 rounded-lg hover:bg-card-hover/50" title="Reset to default blueprint">
              <Trash2 className="w-5 h-5 text-error" />
            </button>
          )}

          {view === 'map' && (
            <div className="flex space-x-2">
              <button onClick={handleZoomOut} className="p-2 bg-card/50 rounded-lg hover:bg-card-hover/50">
                <ZoomOut className="w-5 h-5 text-primary" />
              </button>
              <span className="text-sm text-text-secondary self-center">{Math.round(zoom * 100)}%</span>
              <button onClick={handleZoomIn} className="p-2 bg-card/50 rounded-lg hover:bg-card-hover/50">
                <ZoomIn className="w-5 h-5 text-primary" />
              </button>
            </div>
          )}
        </div>
      </div>

      {view === 'list' ? (
        <div className="space-y-4">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="SEARCH DEVICES..."
              className="w-full bg-card/50 border border-input-border rounded-lg pl-9 pr-3 py-2 text-sm text-text-primary font-mono focus:outline-none focus:border-primary"
            />
          </div>
          {groupedByCategory.length === 0 ? (
            <p className="text-text-tertiary font-mono text-sm text-center py-8">NO DEVICES FOUND</p>
          ) : groupedByCategory.map(([category, items]) => (
            <div key={category}>
              <h4 className="text-xs font-mono font-bold text-fui-accent mb-2 tracking-widest">[ {category} ] ({items.length})</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                {items.map(device => (
                  <DeviceListItem
                    key={device.id}
                    device={device}
                    onDragEnd={handleDragEnd}
                    onClick={handleDeviceSelect}
                    onDeviceSelect={onDeviceSelect}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex">
          <div ref={blueprintRef} className="blueprint-container flex-1 overflow-auto" style={{ position: 'relative' }}>
            <div style={{ transform: `scale(${zoom})`, transformOrigin: 'top left', width: `${100 / zoom}%`, height: `${100 / zoom}%` }}>
              {floorplan ? (
                <img src={floorplan} alt="Floorplan" style={{ width: '100%', height: 'auto', maxWidth: '1200px' }} />
              ) : (
                <BlueprintSVG style={{ width: '100%', height: 'auto', maxWidth: '1200px' }} />
              )}

              {/* User location avatars */}
              {locatedUsers.map(({ user, position }) => (
                <motion.div
                  key={user.id}
                  initial={{ opacity: 0, scale: 0.6 }}
                  animate={{ opacity: 1, scale: 1 }}
                  style={{ position: 'absolute', left: position.x * zoom, top: position.y * zoom, zIndex: 12 }}
                  className="flex flex-col items-center pointer-events-none"
                  title={`${user.name} (${user.type})`}
                >
                  <div
                    className="w-8 h-8 rounded-full overflow-hidden border-2 flex items-center justify-center text-[10px] font-mono font-bold"
                    style={{ borderColor: 'var(--theme-primary)', boxShadow: '0 0 10px color-mix(in srgb, var(--theme-primary) 70%, transparent)' }}
                  >
                    {getGravatarUrl(user.email) ? (
                      <img src={getGravatarUrl(user.email)} alt={user.name} className="w-full h-full object-cover" />
                    ) : (
                      <span className="text-fui-bg">{initialsOf(user.name)}</span>
                    )}
                  </div>
                  <span className="mt-0.5 px-1.5 py-px bg-black/60 border border-fui-border/50 text-[9px] font-mono text-fui-accent">
                    {user.name.toUpperCase()}
                  </span>
                </motion.div>
              ))}

              {positionedDevices.map((device) => (
                <motion.div
                  key={device.id}
                  drag
                  dragConstraints={blueprintRef}
                  onDragEnd={(event, info) => handleDragEnd(device, event, info)}
                  style={{
                    position: 'absolute',
                    left: device.position.x * zoom,
                    top: device.position.y * zoom,
                    zIndex: 10,
                  }}
                  className="cursor-pointer"
                  onClick={() => handleDeviceClick(device)}
                >
                  <DeviceIcon
                    device={device}
                    onRemove={removeDeviceFromBlueprint}
                  />
                </motion.div>
              ))}
              <AnimatePresence>
                {selectedDevice && selectedDevice.position && (
                  <ControlBlade
                    device={selectedDevice}
                    onClose={() => setSelectedDevice(null)}
                    style={{
                      left: selectedDevice.position.x * zoom + 50,
                      top: selectedDevice.position.y * zoom - 150,
                    }}
                  />
                )}
              </AnimatePresence>
            </div>
          </div>

          <div className="ml-6 w-64">
             <div className="flex items-center justify-between mb-2">
               <h3 className="text-lg font-semibold text-primary">Devices</h3>
               <button
                 onClick={() => setIsListExpanded(!isListExpanded)}
                 className="p-1 bg-card/50 rounded-lg hover:bg-card-hover/50"
               >
                 {isListExpanded ? <ChevronUp className="w-4 h-4 text-primary" /> : <ChevronDown className="w-4 h-4 text-primary" />}
               </button>
             </div>
             {isListExpanded && (
               <motion.div
                 initial={{ opacity: 0, height: 0 }}
                 animate={{ opacity: 1, height: 'auto' }}
                 exit={{ opacity: 0, height: 0 }}
                 className="space-y-2"
               >
                 {unpositionedDevices.map((device) => (
                   <DeviceListItem
                     key={device.id}
                     device={device}
                     onDragEnd={handleDragEnd}
                     onClick={handleDeviceSelect}
                     onSelect={setSelectedDevice}
                     onDeviceSelect={onDeviceSelect}
                   />
                 ))}
               </motion.div>
             )}
           </div>
        </div>
      )}
    </div>
  );
};

Blueprint.propTypes = {
  onDeviceSelect: PropTypes.func,
};

Blueprint.displayName = 'Blueprint';

export default Blueprint;
