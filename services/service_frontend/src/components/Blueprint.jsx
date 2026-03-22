import { useState, useEffect, useRef, useCallback, useMemo, memo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Lightbulb, Thermometer, Wifi, ZoomIn, ZoomOut, ChevronDown, ChevronUp, X, AlertTriangle } from 'lucide-react';
import PropTypes from 'prop-types';
import BlueprintSVG from './cassiopeia_blueprint.svg?react';
import ControlBlade from './ControlBlade';
import { API_BASE_URL } from '../config';

const DeviceIcon = memo(({ device, showWarning, onRemove }) => {
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
    <div className="relative">
      <Icon className={`w-8 h-8 ${device.state === 'online' ? 'text-primary' : 'text-text-tertiary'}`} />
      {showWarning && (
        <div
          className="absolute -top-2 -right-2 w-5 h-5 bg-yellow-500 rounded-full flex items-center justify-center cursor-help"
          title={`Not linked to local device. MAC: ${device.mac_address || 'N/A'}`}
        >
          <AlertTriangle className="w-3 h-3 text-black" />
        </div>
      )}
      {!showWarning && (
        <button
          onClick={(e) => { e.stopPropagation(); onRemove(device.id); }}
          className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full flex items-center justify-center text-white text-xs"
        >
          <X className="w-2 h-2" />
        </button>
      )}
    </div>
  );
});

DeviceIcon.displayName = 'DeviceIcon';

DeviceIcon.propTypes = {
  device: PropTypes.object.isRequired,
  showWarning: PropTypes.bool.isRequired,
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

  const showWarning = device.type === 'iot' && !device.linked;

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
        {showWarning && (
          <div
            className="absolute -top-1 -right-1 w-4 h-4 bg-yellow-500 rounded-full flex items-center justify-center"
            title={`Not linked to local device. MAC: ${device.mac_address || 'N/A'}`}
          >
            <AlertTriangle className="w-2 h-2 text-black" />
          </div>
        )}
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

const Blueprint = ({ onDeviceSelect }) => {
  const [devices, setDevices] = useState([]);
  const [zoom, setZoom] = useState(1);
  const [isListExpanded, setIsListExpanded] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const blueprintRef = useRef(null);

  useEffect(() => {
    const fetchDevices = async () => {
      try {
        const response = await fetch(API_BASE_URL + '/api/devices');
        const allDevices = await response.json();
        const alfredDevices = allDevices.filter(device => device.user === 'alfr3d');

        let iotDevices = [];
        try {
          const iotResponse = await fetch(API_BASE_URL + '/api/iot/devices');
          if (iotResponse.ok) {
            iotDevices = await iotResponse.json();
          }
        } catch (iotError) {
          console.error('Error fetching IoT devices:', iotError);
        }

        const mergedDevices = [
          ...alfredDevices.map(d => ({ ...d, type: 'local' })),
          ...iotDevices.map(iot => ({
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
          }))
        ];

        setDevices(mergedDevices);
      } catch (error) {
        console.error('Error fetching devices:', error);
      }
    };

    fetchDevices();
  }, []);

  const positionedDevices = useMemo(() => devices.filter(d => d.position), [devices]);
  const unpositionedDevices = useMemo(() => devices.filter(d => !d.position), [devices]);

  const handleZoomIn = useCallback(() => setZoom(prev => Math.min(prev + 0.2, 3)), []);
  const handleZoomOut = useCallback(() => setZoom(prev => Math.max(prev - 0.2, 0.5)), []);

  const updateDevicePosition = useCallback(async (deviceId, position) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/devices/${deviceId}`, {
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

  return (
    <div className="glass rounded-2xl p-6 h-[800px] relative overflow-auto">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold text-primary drop-shadow-lg">Home Blueprint</h2>
        <div className="flex space-x-2">
          <button onClick={handleZoomOut} className="p-2 bg-card/50 rounded-lg hover:bg-card-hover/50">
            <ZoomOut className="w-5 h-5 text-primary" />
          </button>
          <span className="text-sm text-text-secondary self-center">{Math.round(zoom * 100)}%</span>
          <button onClick={handleZoomIn} className="p-2 bg-card/50 rounded-lg hover:bg-card-hover/50">
            <ZoomIn className="w-5 h-5 text-primary" />
          </button>
        </div>
      </div>

      <div className="flex">
        <div ref={blueprintRef} className="blueprint-container flex-1 overflow-auto" style={{ position: 'relative' }}>
          <div style={{ transform: `scale(${zoom})`, transformOrigin: 'top left', width: `${100 / zoom}%`, height: `${100 / zoom}%` }}>
            <BlueprintSVG style={{ width: '100%', height: 'auto', maxWidth: '1200px' }} />
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
                  showWarning={device.type === 'iot' && !device.linked}
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
    </div>
  );
};

Blueprint.propTypes = {
  onDeviceSelect: PropTypes.func,
};

Blueprint.displayName = 'Blueprint';

export default Blueprint;
