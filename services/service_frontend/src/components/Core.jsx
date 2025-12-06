// src/components/Core.jsx

import { motion } from 'framer-motion';
import { Sun, Lightbulb, Thermometer, Wifi } from 'lucide-react';
import Lottie from 'lottie-react';
import PropTypes from 'prop-types';
import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';
import { getTimeRatio, getSunAngle } from '../utils/timeUtils';
import { useTheme } from '../utils/useTheme';

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

Satellite.propTypes = {
  radius: PropTypes.number.isRequired,
  angle: PropTypes.number.isRequired,
  size: PropTypes.number.isRequired,
  color: PropTypes.string.isRequired,
  glowColor: PropTypes.string.isRequired,
  children: PropTypes.node,
};

const getIcon = (type) => {
  switch (type) {
    case 'light': return Lightbulb;
    case 'thermostat': return Thermometer;
    default: return Wifi;
  }
};

// SVG Reticle Component for Technical HUD Display
const SVGReticle = ({ className = "", animate = true, variant = "crosshair" }) => {
  const animationVariants = {
    smooth: { rotate: 360 },
    tactical: {
      rotate: [0, 90, 85, 180, 175, 270, 265, 360],
      transition: {
        duration: 60,
        repeat: Infinity,
        ease: "linear",
        times: [0, 0.125, 0.125, 0.375, 0.375, 0.625, 0.625, 1]
      }
    }
  };

  const renderVariant = () => {
    switch (variant) {
      case "radar":
        return (
          <>
            {/* Concentric Circles */}
            <circle cx="50" cy="50" r="48" fill="none" stroke="currentColor" strokeWidth="0.5" strokeDasharray="5, 5" className="text-fui-accent" />
            <circle cx="50" cy="50" r="35" fill="none" stroke="currentColor" strokeWidth="0.5" className="text-fui-text" />
            <circle cx="50" cy="50" r="20" fill="none" stroke="currentColor" strokeWidth="0.5" className="text-fui-text" />

            {/* Diagonal Lines */}
            <line x1="10" y1="10" x2="90" y2="90" stroke="currentColor" strokeWidth="0.5" className="text-fui-accent" />
            <line x1="90" y1="10" x2="10" y2="90" stroke="currentColor" strokeWidth="0.5" className="text-fui-accent" />

            {/* Radial Spokes */}
            {[0, 45, 90, 135, 180, 225, 270, 315].map((angle, index) => {
              const radian = (angle * Math.PI) / 180;
              const x2 = 50 + 48 * Math.cos(radian);
              const y2 = 50 + 48 * Math.sin(radian);
              return (
                <line
                  key={index}
                  x1="50"
                  y1="50"
                  x2={x2}
                  y2={y2}
                  stroke="currentColor"
                  strokeWidth="0.5"
                  className="text-fui-text"
                />
              );
            })}
          </>
        );
      case "grid":
        return (
          <>
            {/* Grid Pattern */}
            <defs>
              <pattern id="grid" width="10" height="10" patternUnits="userSpaceOnUse">
                <path d="M 10 0 L 0 0 0 10" fill="none" stroke="currentColor" strokeWidth="0.5" className="text-fui-text" />
              </pattern>
            </defs>
            <rect width="100" height="100" fill="url(#grid)" />

            {/* Radial Spokes */}
            {[0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330].map((angle, index) => {
              const radian = (angle * Math.PI) / 180;
              const x2 = 50 + 48 * Math.cos(radian);
              const y2 = 50 + 48 * Math.sin(radian);
              return (
                <line
                  key={index}
                  x1="50"
                  y1="50"
                  x2={x2}
                  y2={y2}
                  stroke="currentColor"
                  strokeWidth="0.5"
                  className="text-fui-accent"
                />
              );
            })}
          </>
        );
      case "crosshair1":
        return (
          <>
            {/* Inner Solid Arcs */}
            <path
              d="M50 10 A 40 40 0 0 1 90 50"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-fui-text"
            />
            <path
              d="M50 90 A 40 40 0 0 1 10 50"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-fui-text"
            />

            {/* Scale Markers */}
            {[0, 45, 90, 135, 180, 225, 270, 315].map((angle, index) => {
              const radian = (angle * Math.PI) / 180;
              const x1 = 50 + 45 * Math.cos(radian);
              const y1 = 50 + 45 * Math.sin(radian);
              const x2 = 50 + 48 * Math.cos(radian);
              const y2 = 50 + 48 * Math.sin(radian);

              return (
                <line
                  key={index}
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke="currentColor"
                  strokeWidth="0.5"
                  className="text-fui-text"
                />
              );
            })}
          </>
        );
      case "crosshair2":
        return (
          <>
            {/* Outer Dashed Ring */}
            <circle
              cx="50" cy="50" r="48"
              fill="none"
              stroke="currentColor"
              strokeWidth="0.5"
              strokeDasharray="10, 5"
              className="text-fui-text"
            />

            {/* Crosshairs */}
            <line x1="50" y1="5" x2="50" y2="15" stroke="currentColor" strokeWidth="1" className="text-fui-text" />
            <line x1="50" y1="85" x2="50" y2="95" stroke="currentColor" strokeWidth="1" className="text-fui-text" />
            <line x1="5" y1="50" x2="15" y2="50" stroke="currentColor" strokeWidth="1" className="text-fui-text" />
            <line x1="85" y1="50" x2="95" y2="50" stroke="currentColor" strokeWidth="1" className="text-fui-text" />

          </>
        );
      case "crosshair3":
        return (
          <>
            {/* Inner Solid Arcs */}
            <path
              d="M50 10 A 40 40 0 0 1 90 50"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-fui-accent"
            />
            <path
              d="M50 90 A 40 40 0 0 1 10 50"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-fui-accent"
            />

            {/* Crosshairs */}
            <line x1="50" y1="5" x2="50" y2="15" stroke="currentColor" strokeWidth="1" className="text-fui-accent" />
            <line x1="50" y1="85" x2="50" y2="95" stroke="currentColor" strokeWidth="1" className="text-fui-accent" />
            <line x1="5" y1="50" x2="15" y2="50" stroke="currentColor" strokeWidth="1" className="text-fui-accent" />
            <line x1="85" y1="50" x2="95" y2="50" stroke="currentColor" strokeWidth="1" className="text-fui-accent" />

            {/* Scale Markers */}
            {[0, 45, 90, 135, 180, 225, 270, 315].map((angle, index) => {
              const radian = (angle * Math.PI) / 180;
              const x1 = 50 + 45 * Math.cos(radian);
              const y1 = 50 + 45 * Math.sin(radian);
              const x2 = 50 + 48 * Math.cos(radian);
              const y2 = 50 + 48 * Math.sin(radian);

              return (
                <line
                  key={index}
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke="currentColor"
                  strokeWidth="0.5"
                  className="text-fui-accent"
                />
              );
            })}
          </>
        );
      default: // "crosshair"
        return (
          <>
            {/* Outer Dashed Ring */}
            <circle
              cx="50" cy="50" r="48"
              fill="none"
              stroke="currentColor"
              strokeWidth="0.5"
              strokeDasharray="10, 5"
              className="text-fui-accent"
            />

            {/* Inner Solid Arcs */}
            <path
              d="M50 10 A 40 40 0 0 1 90 50"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-fui-text"
            />
            <path
              d="M50 90 A 40 40 0 0 1 10 50"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-fui-text"
            />

            {/* Crosshairs */}
            <line x1="50" y1="5" x2="50" y2="15" stroke="currentColor" strokeWidth="1" className="text-fui-accent" />
            <line x1="50" y1="85" x2="50" y2="95" stroke="currentColor" strokeWidth="1" className="text-fui-accent" />
            <line x1="5" y1="50" x2="15" y2="50" stroke="currentColor" strokeWidth="1" className="text-fui-accent" />
            <line x1="85" y1="50" x2="95" y2="50" stroke="currentColor" strokeWidth="1" className="text-fui-accent" />

            {/* Scale Markers */}
            {[0, 45, 90, 135, 180, 225, 270, 315].map((angle, index) => {
              const radian = (angle * Math.PI) / 180;
              const x1 = 50 + 45 * Math.cos(radian);
              const y1 = 50 + 45 * Math.sin(radian);
              const x2 = 50 + 48 * Math.cos(radian);
              const y2 = 50 + 48 * Math.sin(radian);

              return (
                <line
                  key={index}
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke="currentColor"
                  strokeWidth="0.5"
                  className="text-fui-text"
                />
              );
            })}
          </>
        );
    }
  };

  return (
    <motion.svg
      className={`absolute top-0 left-0 w-full h-full pointer-events-none opacity-40 ${className}`}
      viewBox="0 0 100 100"
      animate={animate ? animationVariants.tactical : {}}
    >
      {renderVariant()}
    </motion.svg>
  );
};

SVGReticle.propTypes = {
  className: PropTypes.string,
  animate: PropTypes.bool,
  variant: PropTypes.oneOf(['crosshair', 'radar', 'crosshair1', 'crosshair2', 'crosshair3', 'grid']),
};

const Core = () => {
  const [animationData, setAnimationData] = useState(null);
  const [isIntroFinished, setIsIntroFinished] = useState(false);
  const [rotationAngle, setRotationAngle] = useState(0);
  const [containers, setContainers] = useState([]);
  const [users, setUsers] = useState([]);
  const [devices, setDevices] = useState([]);
  const [sunAngle, setSunAngle] = useState(0);
  const [reticle1Animate, setReticle1Animate] = useState({ rotate: 0, transition: { duration: 4, ease: "easeInOut" } });
  const [reticle2Animate, setReticle2Animate] = useState({ rotate: 0, transition: { duration: 4, ease: "easeInOut" } });
  const [reticle3Animate, setReticle3Animate] = useState({ rotate: 0, transition: { duration: 4, ease: "easeInOut" } });
  const { themeColors } = useTheme();

  useEffect(() => {
    fetch('/assets/lottie/logo.json')
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

  // Animation logic: Tactical "thinking" rotation after intro finishes
  // Generates stuttering rotation angles with tactical scanning patterns
  useEffect(() => {
    if (isIntroFinished) {
      let timeoutId;
      const triggerTacticalRotation = () => {
        // Create tactical scanning patterns
        const patterns = [
          (Math.random() - 0.5) * 30,  // Small adjustment
          (Math.random() - 0.5) * 45,  // Medium scan
          (Math.random() - 0.5) * 20,  // Fine adjustment
        ];
        const newAngle = patterns[Math.floor(Math.random() * patterns.length)];
        setRotationAngle(newAngle);
        const tacticalDelay = Math.random() * 3000 + 500; // Faster, more erratic timing
        timeoutId = setTimeout(triggerTacticalRotation, tacticalDelay);
      };
      triggerTacticalRotation();
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

  // Effect for reticle 1 independent rotation
  useEffect(() => {
    let timeoutId;
    const updateReticle1 = () => {
      const newAngle = (Math.random() - 0.5) * 180; // -90 to 90
      const duration = Math.random() * 2 + 3; // 3 to 5 seconds
      setReticle1Animate({ rotate: newAngle, transition: { duration, ease: "easeInOut" } });
      timeoutId = setTimeout(updateReticle1, duration * 1000);
    };
    updateReticle1();
    return () => clearTimeout(timeoutId);
  }, []);

  // Effect for reticle 2 independent rotation
  useEffect(() => {
    let timeoutId;
    const updateReticle2 = () => {
      const newAngle = (Math.random() - 0.5) * 180; // -90 to 90
      const duration = Math.random() * 2 + 3; // 3 to 5 seconds
      setReticle2Animate({ rotate: newAngle, transition: { duration, ease: "easeInOut" } });
      timeoutId = setTimeout(updateReticle2, duration * 1000);
    };
    updateReticle2();
    return () => clearTimeout(timeoutId);
  }, []);

  // Effect for reticle 3 independent rotation
  useEffect(() => {
    let timeoutId;
    const updateReticle3 = () => {
      const newAngle = (Math.random() - 0.5) * 180; // -90 to 90
      const duration = Math.random() * 2 + 3; // 3 to 5 seconds
      setReticle3Animate({ rotate: newAngle, transition: { duration, ease: "easeInOut" } });
      timeoutId = setTimeout(updateReticle3, duration * 1000);
    };
    updateReticle3();
    return () => clearTimeout(timeoutId);
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
            options={{ expressions: false }}
          />
        )}
      </motion.div>



        {/* SVG Technical Reticles */}
        <motion.div animate={reticle1Animate} className="absolute inset-0">
          <SVGReticle animate={false} variant="crosshair3" />
        </motion.div>
        <motion.div animate={reticle2Animate} className="absolute inset-0">
          <SVGReticle className="scale-75 opacity-30" animate={false} variant="crosshair2" />
        </motion.div>
        <motion.div animate={reticle3Animate} className="absolute inset-0">
          <SVGReticle className="scale-50 opacity-20" animate={false} variant="crosshair1" />
        </motion.div>

         {/* User Orbit - Outer ring */}
         {/* Orbit calculations: Tactical stuttering rotation over 30 seconds */}
          <motion.div
            className="absolute top-0 left-0 w-full h-full"
            animate={{
              rotate: 360,
              transition: {
                duration: 30,
                repeat: Infinity,
                ease: "linear"
              }
            }}
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
         {/* Orbit calculations: Tactical scanning rotation with stuttering */}
          <motion.div
            className="absolute top-0 left-0 w-full h-full"
            animate={{
              rotate: -360,
              transition: {
                duration: 60,
                repeat: Infinity,
                ease: "linear"
              }
            }}
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
        {/* Orbit calculations: Tactical counter-clockwise rotation with scanning patterns */}
         <motion.div
           className="absolute top-0 left-0 w-full h-full"
           animate={{
             rotate: 360,
             transition: {
               duration: 60,
               repeat: Infinity,
               ease: "linear"
             }
           }}
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
