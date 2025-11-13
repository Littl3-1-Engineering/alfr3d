// src/components/Core.jsx

import { motion } from 'framer-motion';
import { Sun } from 'lucide-react';
import Lottie from 'lottie-react';
import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';

// --- A simplified Satellite component ---
const Satellite = ({ radius, angle, size, color, glowColor, children }) => {
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

const Core = () => {
  const [animationData, setAnimationData] = useState(null);
  const [isIntroFinished, setIsIntroFinished] = useState(false);
  const [rotationAngle, setRotationAngle] = useState(0);
  const [containers, setContainers] = useState([]);
  const [users, setUsers] = useState([]);

  const timeRatio = (new Date().getHours() * 60 + new Date().getMinutes()) / (24 * 60);

  useEffect(() => {
    // Corrected the path to be absolute from the public directory
    fetch('/lottie/logo.json')
      .then(response => response.json())
      .then(data => setAnimationData(data));
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

  // Effect to handle the random "thinking" rotation after the intro
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
      <div className="absolute top-1/2 left-1/2 w-[80%] h-[80%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan-500/20"></div>
      <div className="absolute top-1/2 left-1/2 w-[60%] h-[60%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan-500/20"></div>
      <div className="absolute top-1/2 left-1/2 w-[40%] h-[40%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan-500/20"></div>

      {/* User Orbit - Middle ring */}
      <motion.div
        className="absolute top-0 left-0 w-full h-full"
        animate={{ rotate: 360 }}
        transition={{ duration: 45, repeat: Infinity, ease: "linear" }}
        style={{ zIndex: 10 }}
      >
        {users.map((user, index) => (
          <Satellite
            key={`user-${user.name}`}
            radius={120} // 60% ring radius
            angle={(index / users.length) * 2 * Math.PI}
            size={10}
            color={user.type === 'guest' ? '#fbbf24' : '#10b981'}
            glowColor={user.type === 'guest' ? '#fbbf24' : '#10b981'}
          />
        ))}
      </motion.div>

      {/* Container Orbit - This div rotates on top of everything */}
      <motion.div
        className="absolute top-0 left-0 w-full h-full"
        animate={{ rotate: -360 }}
        transition={{ duration: 45, repeat: Infinity, ease: "linear" }}
        style={{ zIndex: 10 }}
      >
        {containers.map((container, index) => {
          let color, glowColor, size;
          if (container.errors === 0) {
            color = '#10b981'; // Green for healthy
            glowColor = '#10b981';
            size = 8;
          } else if (container.errors === 1) {
            color = '#fbbf24'; // Yellow for unhealthy
            glowColor = '#fbbf24';
            size = 10;
          } else {
            color = '#ef4444'; // Red for critical
            glowColor = '#ef4444';
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
      
      {/* Sun Orbit - This div also rotates on top */}
      <motion.div
        className="absolute top-0 left-0 w-full h-full"
        initial={{ rotate: timeRatio * 360 }}
        animate={{ rotate: 360 + (timeRatio * 360) }}
        transition={{ duration: 86400, repeat: Infinity, ease: "linear" }}
        style={{ zIndex: 10 }}
      >
          <Satellite
            radius={160} // 80% ring radius
            angle={-Math.PI / 2}
            size={24}
            color="transparent"
            glowColor="#fde047"
          >
            <Sun className="w-full h-full text-yellow-300"/>
          </Satellite>
      </motion.div>
    </div>
  );
};

export default Core;