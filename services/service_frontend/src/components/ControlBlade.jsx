import { motion, AnimatePresence } from 'framer-motion';
import { X, Settings, RefreshCw, Thermometer, Lock, Unlock, Fan, Blinds, Play, Pause, Volume2 } from 'lucide-react';
import { useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import { API_BASE_URL } from '../config';

const ControlBlade = ({ device, onClose, style }) => {
  const [power, setPower] = useState(false);
  const [brightness, setBrightness] = useState(75);
  const [currentTemp, setCurrentTemp] = useState(70);
  const [targetTemp, setTargetTemp] = useState(70);
  const [lockState, setLockState] = useState('unlocked');
  const [fanSpeed, setFanSpeed] = useState('off');
  const [coverPosition, setCoverPosition] = useState(0);
  const [volume, setVolume] = useState(50);
  const [sensorValue, setSensorValue] = useState(null);
  const [sensorUnit, setSensorUnit] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!device?.last_state) return;

    const state = device.last_state;
    const attrs = state.attributes || {};

    if (device.device_type === 'light') {
      setPower(state.state === 'on');
      setBrightness(attrs.brightness || 75);
    } else if (device.device_type === 'switch') {
      setPower(state.state === 'on');
    } else if (device.device_type === 'climate') {
      setPower(state.state === 'heat' || state.state === 'cool' || state.state === 'auto');
      setCurrentTemp(attrs.current_temperature || 70);
      setTargetTemp(attrs.temperature || 70);
    } else if (device.device_type === 'lock') {
      setLockState(state.state);
    } else if (device.device_type === 'fan') {
      setPower(state.state === 'on');
      setFanSpeed(attrs.percentage || 'off');
    } else if (device.device_type === 'cover') {
      setPower(state.state === 'open');
      setCoverPosition(attrs.current_position || 0);
    } else if (device.device_type === 'media_player') {
      setPower(state.state === 'playing');
      setVolume(attrs.volume_level * 100 || 50);
    } else if (device.device_type === 'sensor' || device.device_type === 'binary_sensor') {
      const unit = attrs.unit_of_measurement || '';
      setSensorUnit(unit);
      if (attrs.temperature) {
        setSensorValue(attrs.temperature);
        setSensorUnit(unit || '°');
      } else if (attrs.current) {
        setSensorValue(attrs.current);
        setSensorUnit(unit || 'A');
      } else if (attrs.humidity) {
        setSensorValue(attrs.humidity);
        setSensorUnit('%');
      } else if (attrs.battery_level) {
        setSensorValue(attrs.battery_level);
        setSensorUnit('%');
      } else if (state.state !== undefined) {
        setSensorValue(state.state);
      }
    }
  }, [device?.last_state, device?.device_type]);

  const sendCommand = useCallback(async (command, params = {}) => {
    if (!device?.id || !device?.source) return false;

    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/iot/devices/${device.id}/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command, ...params })
      });
      return response.ok;
    } catch (error) {
      console.error('Error sending command:', error);
      return false;
    } finally {
      setLoading(false);
    }
  }, [device?.id, device?.source]);

  const handlePowerToggle = useCallback(async () => {
    const newState = !power;
    setPower(newState);
    const success = await sendCommand(newState ? 'turn_on' : 'turn_off');
    if (!success) setPower(!newState);
  }, [power, sendCommand]);

  const handleBrightnessChange = useCallback(async (value) => {
    const newBrightness = parseInt(value, 10);
    setBrightness(newBrightness);
    const success = await sendCommand('set_brightness', { params: { brightness: newBrightness } });
    if (!success) setBrightness(75);
  }, [sendCommand]);

  const handleTemperatureChange = useCallback(async (newTemp) => {
    setTargetTemp(newTemp);
    const success = await sendCommand('set_temperature', { params: { temperature: newTemp } });
    if (!success) setTargetTemp(70);
  }, [sendCommand]);

  const handleLockToggle = useCallback(async () => {
    const newState = lockState === 'locked' ? 'unlocked' : 'locked';
    setLockState(newState);
    const success = await sendCommand(newState === 'locked' ? 'lock' : 'unlock');
    if (!success) setLockState(lockState);
  }, [lockState, sendCommand]);

  const handleFanSpeedChange = useCallback(async (speed) => {
    setFanSpeed(speed);
    const success = await sendCommand('set_speed', { params: { speed } });
    if (!success) setFanSpeed('off');
  }, [sendCommand]);

  const handleCoverPositionChange = useCallback(async (position) => {
    setCoverPosition(position);
    const success = await sendCommand('set_position', { params: { position } });
    if (!success) setCoverPosition(0);
  }, [sendCommand]);

  const handleMediaToggle = useCallback(async () => {
    const newState = !power;
    setPower(newState);
    const success = await sendCommand(newState ? 'media_play' : 'media_pause');
    if (!success) setPower(!newState);
  }, [power, sendCommand]);

  const handleVolumeChange = useCallback(async (value) => {
    const newVolume = parseInt(value, 10);
    setVolume(newVolume);
    const success = await sendCommand('volume_set', { params: { volume: newVolume } });
    if (!success) setVolume(50);
  }, [sendCommand]);

  const isSmartHomeDevice = device?.source !== undefined;
  const deviceType = device?.device_type || device?.deviceType;

  const renderLightControls = () => (
    <>
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <span className="text-text-secondary">Power</span>
          {loading && <RefreshCw className="w-4 h-4 text-primary animate-spin" />}
        </div>
        <motion.button
          whileTap={{ scale: 0.95 }}
          onClick={handlePowerToggle}
          disabled={loading || !isSmartHomeDevice}
          className={`w-12 h-6 rounded-full p-1 transition-colors ${
            power ? 'bg-primary' : 'bg-border-secondary'
          } ${(!isSmartHomeDevice) ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          <motion.div
            animate={{ x: power ? 18 : 0 }}
            className="w-4 h-4 bg-text-inverse rounded-full"
          />
        </motion.button>
      </div>

      <div>
        <div className="flex justify-between mb-2">
          <span className="text-text-secondary">Brightness</span>
          <span className="text-primary font-mono">{brightness}%</span>
        </div>
        <input
          type="range"
          min="0"
          max="100"
          value={brightness}
          onChange={(e) => handleBrightnessChange(e.target.value)}
          disabled={!isSmartHomeDevice || loading || !power}
          className={`w-full h-2 bg-border-secondary rounded-lg appearance-none cursor-pointer slider ${
            (!isSmartHomeDevice || !power) ? 'opacity-50 cursor-not-allowed' : ''
          }`}
        />
      </div>
    </>
  );

  const renderClimateControls = () => (
    <>
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Thermometer className="w-5 h-5 text-primary" />
          <span className="text-text-secondary">Climate</span>
          {loading && <RefreshCw className="w-4 h-4 text-primary animate-spin" />}
        </div>
        <span className="text-primary font-mono">
          {device?.last_state?.attributes?.current_temperature || '--'}°
        </span>
      </div>

      <div>
        <div className="flex justify-between mb-2">
          <span className="text-text-secondary">Target Temperature</span>
          <span className="text-primary font-mono">{targetTemp}°F</span>
        </div>
        <div className="flex space-x-2">
          <button
            onClick={() => handleTemperatureChange(Math.max(50, targetTemp - 1))}
            disabled={!isSmartHomeDevice || loading}
            className="flex-1 py-2 bg-card rounded-lg text-text-secondary hover:bg-card-hover transition-colors disabled:opacity-50"
          >
            -
          </button>
          <button
            onClick={() => handleTemperatureChange(Math.min(90, targetTemp + 1))}
            disabled={!isSmartHomeDevice || loading}
            className="flex-1 py-2 bg-card rounded-lg text-text-secondary hover:bg-card-hover transition-colors disabled:opacity-50"
          >
            +
          </button>
        </div>
      </div>
    </>
  );

  const renderLockControls = () => (
    <div className="flex items-center justify-between">
      <div className="flex items-center space-x-2">
        {lockState === 'locked' ? (
          <Lock className="w-5 h-5 text-primary" />
        ) : (
          <Unlock className="w-5 h-5 text-text-secondary" />
        )}
        <span className="text-text-secondary">
          {lockState === 'locked' ? 'Locked' : 'Unlocked'}
        </span>
        {loading && <RefreshCw className="w-4 h-4 text-primary animate-spin" />}
      </div>
      <motion.button
        whileTap={{ scale: 0.95 }}
        onClick={handleLockToggle}
        disabled={loading || !isSmartHomeDevice}
        className={`px-4 py-2 rounded-lg transition-colors ${
          lockState === 'locked'
            ? 'bg-red-600 text-white'
            : 'bg-green-600 text-white'
        } ${(!isSmartHomeDevice) ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        {lockState === 'locked' ? 'Unlock' : 'Lock'}
      </motion.button>
    </div>
  );

  const renderFanControls = () => (
    <>
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Fan className={`w-5 h-5 ${power ? 'text-primary animate-spin' : 'text-text-secondary'}`} />
          <span className="text-text-secondary">Fan</span>
          {loading && <RefreshCw className="w-4 h-4 text-primary animate-spin" />}
        </div>
        <motion.button
          whileTap={{ scale: 0.95 }}
          onClick={handlePowerToggle}
          disabled={loading || !isSmartHomeDevice}
          className={`w-12 h-6 rounded-full p-1 transition-colors ${
            power ? 'bg-primary' : 'bg-border-secondary'
          } ${(!isSmartHomeDevice) ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          <motion.div
            animate={{ x: power ? 18 : 0 }}
            className="w-4 h-4 bg-text-inverse rounded-full"
          />
        </motion.button>
      </div>

      <div>
        <div className="flex justify-between mb-2">
          <span className="text-text-secondary">Speed</span>
          <span className="text-primary font-mono capitalize">{fanSpeed}</span>
        </div>
        <div className="flex space-x-2">
          {['off', 'low', 'medium', 'high'].map((speed) => (
            <button
              key={speed}
              onClick={() => handleFanSpeedChange(speed)}
              disabled={!isSmartHomeDevice || loading}
              className={`flex-1 py-2 rounded-lg text-xs transition-colors ${
                fanSpeed === speed
                  ? 'bg-primary text-white'
                  : 'bg-card text-text-secondary hover:bg-card-hover'
              } disabled:opacity-50`}
            >
              {speed}
            </button>
          ))}
        </div>
      </div>
    </>
  );

  const renderCoverControls = () => (
    <>
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Blinds className="w-5 h-5 text-primary" />
          <span className="text-text-secondary">Blinds</span>
          {loading && <RefreshCw className="w-4 h-4 text-primary animate-spin" />}
        </div>
        <span className="text-primary font-mono">{coverPosition}%</span>
      </div>

      <div>
        <div className="flex justify-between mb-2">
          <span className="text-text-secondary">Position</span>
        </div>
        <input
          type="range"
          min="0"
          max="100"
          value={coverPosition}
          onChange={(e) => handleCoverPositionChange(parseInt(e.target.value, 10))}
          disabled={!isSmartHomeDevice || loading}
          className={`w-full h-2 bg-border-secondary rounded-lg appearance-none cursor-pointer slider ${
            (!isSmartHomeDevice) ? 'opacity-50 cursor-not-allowed' : ''
          }`}
        />
      </div>

      <div className="flex space-x-2">
        <button
          onClick={() => handleCoverPositionChange(0)}
          disabled={!isSmartHomeDevice || loading}
          className="flex-1 py-2 bg-card rounded-lg text-text-secondary hover:bg-card-hover transition-colors disabled:opacity-50"
        >
          Close
        </button>
        <button
          onClick={() => handleCoverPositionChange(100)}
          disabled={!isSmartHomeDevice || loading}
          className="flex-1 py-2 bg-card rounded-lg text-text-secondary hover:bg-card-hover transition-colors disabled:opacity-50"
        >
          Open
        </button>
      </div>
    </>
  );

  const renderMediaControls = () => (
    <>
      <div className="flex items-center justify-center py-4">
        <motion.button
          whileTap={{ scale: 0.95 }}
          onClick={handleMediaToggle}
          disabled={loading || !isSmartHomeDevice}
          className={`w-16 h-16 rounded-full flex items-center justify-center transition-colors ${
            power ? 'bg-primary' : 'bg-border-secondary'
          } ${(!isSmartHomeDevice) ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          {power ? (
            <Pause className="w-8 h-8 text-white" />
          ) : (
            <Play className="w-8 h-8 text-white ml-1" />
          )}
        </motion.button>
      </div>

      <div>
        <div className="flex justify-between mb-2">
          <div className="flex items-center space-x-2">
            <Volume2 className="w-4 h-4 text-text-secondary" />
            <span className="text-text-secondary">Volume</span>
          </div>
          <span className="text-primary font-mono">{volume}%</span>
        </div>
        <input
          type="range"
          min="0"
          max="100"
          value={volume}
          onChange={(e) => handleVolumeChange(e.target.value)}
          disabled={!isSmartHomeDevice || loading}
          className={`w-full h-2 bg-border-secondary rounded-lg appearance-none cursor-pointer slider ${
            (!isSmartHomeDevice) ? 'opacity-50 cursor-not-allowed' : ''
          }`}
        />
      </div>
    </>
  );

  const renderDeviceControls = () => {
    switch (deviceType) {
      case 'light':
        return renderLightControls();
      case 'switch':
        return (
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">Power</span>
            {loading && <RefreshCw className="w-4 h-4 text-primary animate-spin" />}
            <motion.button
              whileTap={{ scale: 0.95 }}
              onClick={handlePowerToggle}
              disabled={loading || !isSmartHomeDevice}
              className={`w-12 h-6 rounded-full p-1 transition-colors ${
                power ? 'bg-primary' : 'bg-border-secondary'
              } ${(!isSmartHomeDevice) ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <motion.div
                animate={{ x: power ? 18 : 0 }}
                className="w-4 h-4 bg-text-inverse rounded-full"
              />
            </motion.button>
          </div>
        );
      case 'climate':
      case 'thermostat':
        return renderClimateControls();
      case 'lock':
        return renderLockControls();
      case 'fan':
        return renderFanControls();
      case 'cover':
        return renderCoverControls();
      case 'media_player':
        return renderMediaControls();
      case 'sensor':
      case 'binary_sensor':
        return (
          <div className="space-y-4">
            <div className="flex items-center justify-center py-4">
              <div className="text-center">
                <div className="text-4xl font-bold text-primary">
                  {sensorValue !== null ? sensorValue : '--'}
                </div>
                <div className="text-sm text-text-secondary">{sensorUnit}</div>
              </div>
            </div>
            <div className="text-xs text-text-tertiary text-center">
              {device.last_state?.state === 'on' ? 'Active' : device.last_state?.state === 'off' ? 'Inactive' : device.last_state?.state || 'Unknown'}
            </div>
          </div>
        );
      default:
        return (
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">Power</span>
            {loading && <RefreshCw className="w-4 h-4 text-primary animate-spin" />}
            <motion.button
              whileTap={{ scale: 0.95 }}
              onClick={handlePowerToggle}
              disabled={loading || !isSmartHomeDevice}
              className={`w-12 h-6 rounded-full p-1 transition-colors ${
                power ? 'bg-primary' : 'bg-border-secondary'
              } ${(!isSmartHomeDevice) ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <motion.div
                animate={{ x: power ? 18 : 0 }}
                className="w-4 h-4 bg-text-inverse rounded-full"
              />
            </motion.button>
          </div>
        );
    }
  };

  return (
    <AnimatePresence>
      {device && (
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.9 }}
          transition={{ duration: 0.2 }}
          className="absolute w-80 glass z-50 p-6 rounded-2xl shadow-lg"
          style={style}
        >
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl font-bold text-primary drop-shadow-lg">{device.name}</h2>
            <button
              onClick={onClose}
              className="p-2 rounded-full hover:bg-card-hover transition-colors"
            >
              <X className="w-5 h-5 text-text-secondary" />
            </button>
          </div>

          <div className="space-y-6">
            {renderDeviceControls()}

            {isSmartHomeDevice && (
              <div className="text-xs text-text-tertiary space-y-1">
                <p>Source: {device.source === 'homeassistant' ? 'Home Assistant' : device.source === 'smartthings' ? 'SmartThings' : 'Unknown'}</p>
                <p>Room: {device.room || 'Unknown'}</p>
                <p>Type: {deviceType}</p>
                <p>Online: {device.online ? 'Yes' : 'No'}</p>
              </div>
            )}

            <button className="w-full flex items-center justify-center space-x-2 py-3 bg-card/50 rounded-lg hover:bg-card-hover/50 transition-colors">
              <Settings className="w-5 h-5 text-primary" />
              <span className="text-text-secondary">Advanced Settings</span>
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

ControlBlade.propTypes = {
  device: PropTypes.object.isRequired,
  onClose: PropTypes.func.isRequired,
  style: PropTypes.object,
};

export default ControlBlade;
