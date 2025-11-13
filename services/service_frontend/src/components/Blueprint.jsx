import { motion } from 'framer-motion';
import { Lightbulb, Thermometer, Wifi } from 'lucide-react';

const devices = [
  { id: 1, name: 'Living Room Light', type: 'light', x: 200, y: 150, active: true },
  { id: 2, name: 'Kitchen Thermostat', type: 'thermostat', x: 400, y: 200, active: false },
  { id: 3, name: 'Bedroom Hub', type: 'hub', x: 300, y: 350, active: true },
];

const Blueprint = ({ onDeviceSelect }) => {
  const getIcon = (type) => {
    switch (type) {
      case 'light': return Lightbulb;
      case 'thermostat': return Thermometer;
      default: return Wifi;
    }
  };

  return (
    <div className="glass rounded-2xl p-6 h-[600px] relative overflow-hidden">
      <h2 className="text-xl font-bold text-cyan-400 mb-4 drop-shadow-lg">Home Blueprint</h2>
      
      {/* SVG Floor Plan */}
      <svg width="600" height="500" className="w-full h-full">
        {/* House outline */}
        <rect x="50" y="100" width="500" height="350" fill="none" stroke="rgba(6, 182, 212, 0.3)" strokeWidth="2" />
        
        {/* Rooms */}
        <rect x="50" y="100" width="200" height="200" fill="none" stroke="rgba(6, 182, 212, 0.2)" strokeWidth="1" />
        <rect x="250" y="100" width="200" height="200" fill="none" stroke="rgba(6, 182, 212, 0.2)" strokeWidth="1" />
        <rect x="50" y="300" width="200" height="150" fill="none" stroke="rgba(6, 182, 212, 0.2)" strokeWidth="1" />
        <rect x="250" y="300" width="300" height="150" fill="none" stroke="rgba(6, 182, 212, 0.2)" strokeWidth="1" />
        
        {/* Room labels */}
        <text x="150" y="190" textAnchor="middle" className="fill-cyan-400 text-sm">Living</text>
        <text x="350" y="190" textAnchor="middle" className="fill-cyan-400 text-sm">Kitchen</text>
        <text x="150" y="380" textAnchor="middle" className="fill-cyan-400 text-sm">Bedroom</text>
        <text x="400" y="380" textAnchor="middle" className="fill-cyan-400 text-sm">Bathroom</text>
        
        {/* Devices */}
        {devices.map((device) => {
          const Icon = getIcon(device.type);
          return (
            <motion.g
              key={device.id}
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ delay: device.id * 0.2, duration: 0.5 }}
              whileHover={{ scale: 1.2 }}
              onClick={() => onDeviceSelect(device)}
              className="cursor-pointer"
            >
              <circle
                cx={device.x}
                cy={device.y}
                r="20"
                fill={device.active ? "rgba(6, 182, 212, 0.3)" : "rgba(100, 116, 139, 0.3)"}
                stroke={device.active ? "#06b6d4" : "#64748b"}
                strokeWidth="2"
                style={{
                  filter: device.active ? 'drop-shadow(0 0 8px #06b6d4)' : 'none'
                }}
              />
              <Icon
                x={device.x - 10}
                y={device.y - 10}
                width="20"
                height="20"
                className={device.active ? "text-cyan-400" : "text-gray-400"}
              />
              {device.active && (
                <motion.circle
                  cx={device.x}
                  cy={device.y}
                  r="25"
                  fill="none"
                  stroke="#06b6d4"
                  strokeWidth="1"
                  opacity="0.5"
                  animate={{ scale: [1, 1.5, 1], opacity: [0.5, 0, 0.5] }}
                  transition={{ duration: 2, repeat: Infinity }}
                />
              )}
            </motion.g>
          );
        })}
      </svg>
    </div>
  );
};

export default Blueprint;