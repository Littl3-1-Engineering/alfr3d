import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Lightbulb, Thermometer, Wifi, ZoomIn, ZoomOut, ChevronDown, ChevronUp, X } from 'lucide-react';
import BlueprintSVG from './cassiopeia_blueprint.svg?react';
import ControlBlade from './ControlBlade';
import { API_BASE_URL } from '../config';

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
        // Filter devices belonging to 'alfr3d' user
        const alfredDevices = allDevices.filter(device => device.user === 'alfr3d');
        setDevices(alfredDevices);
      } catch (error) {
        console.error('Error fetching devices:', error);
      }
    };

    fetchDevices();
  }, []);

  const positionedDevices = devices.filter(d => d.position);
  const unpositionedDevices = devices.filter(d => !d.position);

  const getIcon = (type) => {
    switch (type) {
      case 'light': return Lightbulb;
      case 'thermostat': return Thermometer;
      default: return Wifi;
    }
  };

  const handleZoomIn = () => setZoom(prev => Math.min(prev + 0.2, 3));
  const handleZoomOut = () => setZoom(prev => Math.max(prev - 0.2, 0.5));

  const updateDevicePosition = async (deviceId, position) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/devices/${deviceId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ position }),
      });
      if (response.ok) {
        // Update local state
        setDevices(prev => prev.map(d => d.id === deviceId ? { ...d, position } : d));
      } else {
        console.error('Failed to update device position');
      }
    } catch (error) {
      console.error('Error updating device position:', error);
    }
  };

  const handleDragEnd = (device, event, info) => {
    if (!blueprintRef.current) return;
    const rect = blueprintRef.current.getBoundingClientRect();
    const x = (info.point.x - rect.left) / zoom;
    const y = (info.point.y - rect.top) / zoom;
    updateDevicePosition(device.id, { x, y });
  };

  const removeDeviceFromBlueprint = (deviceId) => {
    updateDevicePosition(deviceId, null);
  };

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
        {/* Detailed Floor Plan */}
        <div ref={blueprintRef} className="blueprint-container flex-1 overflow-auto" style={{ position: 'relative' }}>
          <div style={{ transform: `scale(${zoom})`, transformOrigin: 'top left', width: `${100 / zoom}%`, height: `${100 / zoom}%` }}>
            <BlueprintSVG style={{ width: '100%', height: 'auto', maxWidth: '1200px' }} />
            {/* Positioned Devices */}
            {positionedDevices.map((device) => {
              const Icon = getIcon(device.type);
              return (
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
                  onClick={() => { setSelectedDevice(device); onDeviceSelect && onDeviceSelect(device); }}
                >
                  <div className="relative">
                    <Icon className={`w-8 h-8 ${device.state === 'online' ? 'text-primary' : 'text-text-tertiary'}`} />
                    <button
                      onClick={(e) => { e.stopPropagation(); removeDeviceFromBlueprint(device.id); }}
                      className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full flex items-center justify-center text-white text-xs"
                    >
                      <X className="w-2 h-2" />
                    </button>
                  </div>
                </motion.div>
              );
            })}
            {/* ControlBlade for selected device */}
            <AnimatePresence>
              {selectedDevice && selectedDevice.position && (
                <ControlBlade
                  device={selectedDevice}
                  onClose={() => setSelectedDevice(null)}
                  style={{
                    left: selectedDevice.position.x * zoom + 50, // Offset to the right of icon
                    top: selectedDevice.position.y * zoom - 150, // Above icon
                  }}
                />
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Devices List */}
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
              {unpositionedDevices.map((device) => {
                const Icon = getIcon(device.type);
                return (
                  <motion.div
                    key={device.id}
                    drag
                    dragConstraints={{ left: 0, top: 0, right: 0, bottom: 0 }} // Allow drag anywhere
                    onDragEnd={(event, info) => handleDragEnd(device, event, info)}
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: device.id * 0.1, duration: 0.3 }}
                    className="flex items-center p-2 bg-card/50 rounded-lg cursor-pointer hover:bg-card-hover/50"
                    onClick={() => { setSelectedDevice(device); onDeviceSelect && onDeviceSelect(device); }}
                  >
                    <Icon className={`w-6 h-6 mr-3 ${device.state === 'online' ? 'text-primary' : 'text-text-tertiary'}`} />
                    <div>
                      <div className="text-sm font-medium text-text-inverse">{device.name}</div>
                      <div className="text-xs text-text-tertiary">{device.type} - {device.state}</div>
                    </div>
                  </motion.div>
                );
              })}
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Blueprint;