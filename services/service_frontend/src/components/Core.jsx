// src/components/Core.jsx

import { motion } from 'framer-motion';
import { Sun, Lightbulb, Thermometer, Wifi } from 'lucide-react';
import Lottie from 'lottie-react';
import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';
import { getTimeRatio, getSunAngle } from '../utils/timeUtils';
import { useTheme } from '../utils/ThemeContext';

// --- A simplified Satellite component ---
const Satellite = ({ radius, angle, size, color, glowColor, children }) => {
  // Satellite positioning math: Convert polar coordinates (radius, angle) to Cartesian (x, y)
  // Center at 50% (middle of container), scale radius to fit within 0-100% range
  const x = 50 + (radius / 200) * 50 * Math.cos(angle);
  const y = 50 + (radius / 200) * 50 * Math.sin(angle);

  return (
    <div
      className="absolute"
      style={{
        width: size,
        height: size,
        top: `${y}%`,
        left: `${x}%`,
        transform: 'translate(-50%, -50%)',
        backgroundColor: color,
        borderRadius: '50%',
        boxShadow: `0 0 12px ${glowColor}`,
      }}
    >
      {children}
    </div>
  );
};

const getIcon = (type) => {
  switch (type) {
    case 'light': return Lightbulb;
    case 'thermostat': return Thermometer;
    default: return Wifi;
  }
};

const Core = () => {
  const [animationData, setAnimationData] = useState(null);
  const [isIntroFinished, setIsIntroFinished] = useState(false);
  const [rotationAngle, setRotationAngle] = useState(0);
  const [containers, setContainers] = useState([]);
  const [users, setUsers] = useState([]);
  const [devices, setDevices] = useState([]);
  const [sunAngle, setSunAngle] = useState(0);
  const { themeColors } = useTheme();

  useEffect(() => {
    // Corrected the path to be absolute from the public directory
    fetch('/lottie/logo.json')
      .then(response => response.json())
      .then(data => setAnimationData(data))
      .catch(error => console.error('Error fetching animation data:', error));
  }, []);

  useEffect(() => {
    const fetchContainers = async () => {
      try {
        const response = await fetch(API_BASE_URL + '/api/containers');
        const data = await response.json();
        setContainers(data);
      } catch (error) {
        console.error('Error fetching containers:', error);
        // Fallback dummy data for testing
        setContainers([{ name: 'test-container', errors: 0 }]);
      }
    };
    fetchContainers();
    const interval = setInterval(fetchContainers, 10000); // Update every 10 seconds
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const fetchUsers = async () => {
      try {
        const response = await fetch(API_BASE_URL + '/api/users?online=true');
        const data = await response.json();
        setUsers(data);
      } catch (error) {
        console.error('Error fetching users:', error);
        // Fallback dummy data for testing
        setUsers([{ name: 'test-user', type: 'user' }]);
      }
    };
    fetchUsers();
    const interval = setInterval(fetchUsers, 5000); // Update every 5 seconds
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const fetchDevices = async () => {
      try {
        const response = await fetch(API_BASE_URL + '/api/devices');
        const data = await response.json();
        setDevices(data);
      } catch (error) {
        console.error('Error fetching devices:', error);
        // Fallback dummy data for testing
        setDevices([{ id: 1, name: 'test-device', type: 'light', user: 'alfr3d', state: 'online' }]);
      }
    };
    fetchDevices();
    const interval = setInterval(fetchDevices, 10000); // Update every 10 seconds
    return () => clearInterval(interval);
  }, []);

  // Animation logic: Random "thinking" rotation after intro finishes
  // Generates random rotation angles (-30° to +30°) at irregular intervals (1-5 seconds)
  // to simulate AI "thinking" behavior
  useEffect(() => {
    if (isIntroFinished) {
      let timeoutId;
      const triggerRandomRotation = () => {
        const newAngle = (Math.random() - 0.5) * 60;
        setRotationAngle(newAngle);
        const randomDelay = Math.random() * 4000 + 1000;
        timeoutId = setTimeout(triggerRandomRotation, randomDelay);
      };
      triggerRandomRotation();
      return () => clearTimeout(timeoutId);
    }
  }, [isIntroFinished]);

  // Effect to update sun angle based on time
  useEffect(() => {
    const updateSunAngle = () => {
      const timeRatio = getTimeRatio();
      const angle = getSunAngle(timeRatio);
      setSunAngle(angle);
    };
    updateSunAngle();
    const interval = setInterval(updateSunAngle, 60000); // Update every minute
    return () => clearInterval(interval);
  }, []);

  return (
    // Responsive container that maintains a square aspect ratio
    <div className="relative w-full max-w-[450px] aspect-square">
      
      <motion.div
        className="absolute inset-0"
        animate={{ rotate: rotationAngle, scale: 0.35 }}
        transition={{ duration: 0.7, ease: "easeInOut" }}
        style={{ originX: '50%', originY: '50%', zIndex: 1 }}
      >
        {animationData && (
          <Lottie
            animationData={animationData}
            loop={false}
            autoplay={true}
            onComplete={() => setIsIntroFinished(true)}
          />
        )}
      </motion.div>

      {/* The Rings - Positioned on top of the Lottie animation */}
      <div className="absolute top-1/2 left-1/2 w-[80%] h-[80%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary/20"></div>
      <div className="absolute top-1/2 left-1/2 w-[60%] h-[60%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary/20"></div>
      <div className="absolute top-1/2 left-1/2 w-[40%] h-[40%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary/20"></div>

       {/* User Orbit - Outer ring */}
       {/* Orbit calculations: Rotates the entire ring -360° over 45 seconds linearly
          Users are positioned evenly around the circle based on their index */}
       <motion.div
         className="absolute top-0 left-0 w-full h-full"
         animate={{ rotate: -360 }}
         transition={{ duration: 45, repeat: Infinity, ease: "linear" }}
         style={{ zIndex: 10 }}
       >
         {users.map((user, index) => (
           <Satellite
             key={`user-${user.name}`}
             radius={160} // 80% ring radius
             angle={(index / users.length) * 2 * Math.PI}
             size={10}
             color={user.type === 'guest' ? themeColors.warning : themeColors.success}
             glowColor={user.type === 'guest' ? themeColors.warning : themeColors.success}
           />
         ))}
       </motion.div>

       {/* Alfr3d Devices Orbit - Middle ring */}
       {/* Orbit calculations: Rotates the entire ring 360° over 45 seconds linearly
          Alfr3d devices are positioned evenly around the circle based on their index */}
       <motion.div
         className="absolute top-0 left-0 w-full h-full"
         animate={{ rotate: 360 }}
         transition={{ duration: 45, repeat: Infinity, ease: "linear" }}
         style={{ zIndex: 10 }}
       >
         {devices.filter(device => device.user === 'alfr3d').map((device, index) => {
           const Icon = getIcon(device.type);
           const deviceColor = device.state === 'online' ? themeColors.success : themeColors.warning;
           return (
             <Satellite
               key={`device-${device.id}`}
               radius={120} // 60% ring radius
               angle={(index / devices.filter(d => d.user === 'alfr3d').length) * 2 * Math.PI}
               size={12}
               color="transparent"
               glowColor={deviceColor}
             >
               <Icon className="w-full h-full" style={{ color: deviceColor }} />
             </Satellite>
           );
         })}
       </motion.div>

       {/* Container Orbit - This div rotates on top of everything */}
      {/* Orbit calculations: Rotates counter-clockwise (-360°) over 45 seconds
         Containers positioned evenly around inner ring, color/size based on error count */}
      <motion.div
        className="absolute top-0 left-0 w-full h-full"
        animate={{ rotate: -360 }}
        transition={{ duration: 45, repeat: Infinity, ease: "linear" }}
        style={{ zIndex: 10 }}
      >
        {containers.map((container, index) => {
          let color, glowColor, size;
          if (container.errors === 0) {
            color = themeColors.success; // Green for healthy
            glowColor = themeColors.success;
            size = 8;
          } else if (container.errors === 1) {
            color = themeColors.warning; // Yellow for unhealthy
            glowColor = themeColors.warning;
            size = 10;
          } else {
            color = themeColors.error; // Red for critical
            glowColor = themeColors.error;
            size = 12;
          }
          return (
            <Satellite
              key={`container-${container.name}`}
              radius={80} // 40% ring radius
              angle={(index / containers.length) * 2 * Math.PI}
              size={size}
              color={color}
              glowColor={glowColor}
            />
          );
        })}
      </motion.div>
      
        {/* Sun Orbit - Positioned based on time */}
        <div className="absolute top-0 left-0 w-full h-full" style={{ zIndex: 10 }}>
           <Satellite
             radius={240} // Outside the rings
             angle={sunAngle}
             size={24}
             color="transparent"
             glowColor={themeColors.warning}
           >
             <Sun className="w-full h-full" style={{ color: themeColors.warning }}/>
           </Satellite>
        </div>
    </div>
  );
};

export default Core;