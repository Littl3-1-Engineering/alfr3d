import { motion } from 'framer-motion';
import { Lightbulb, Power, Thermometer, Fan, Blinds, Lock, Unlock, Play, Pause, X, RefreshCw } from 'lucide-react';
import { useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import { API_BASE_URL } from '../config';
import { apiFetch } from '../utils/apiClient';

const TYPE_ICONS = {
  light: Lightbulb,
  switch: Power,
  climate: Thermometer,
  thermostat: Thermometer,
  fan: Fan,
  cover: Blinds,
  lock: Lock,
  media_player: Play,
};

const FAN_SPEEDS = ['off', 'low', 'medium', 'high'];

// Compact single-tile counterpart to ControlBlade.jsx: one toggle + one contextual dial per
// device, sized to fit up to 10 favorites in a grid rather than one full anchored popover per
// device. Talks to the same /api/iot/devices/{id}/control endpoint and command names.
const FavoriteDeviceTile = ({ device, canControl, editMode, onRemove }) => {
  const deviceType = device.device_type;
  const Icon = TYPE_ICONS[deviceType] || Power;
  const state = device.last_state || {};
  const attrs = state.attributes || {};

  const [power, setPower] = useState(false);
  const [brightness, setBrightness] = useState(75);
  const [targetTemp, setTargetTemp] = useState(70);
  const [lockState, setLockState] = useState('unlocked');
  const [fanSpeed, setFanSpeed] = useState('off');
  const [coverPosition, setCoverPosition] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (deviceType === 'light') {
      setPower(state.state === 'on');
      setBrightness(attrs.brightness || 75);
    } else if (deviceType === 'switch') {
      setPower(state.state === 'on');
    } else if (deviceType === 'climate' || deviceType === 'thermostat') {
      setPower(['heat', 'cool', 'auto'].includes(state.state));
      setTargetTemp(attrs.temperature || 70);
    } else if (deviceType === 'lock') {
      setLockState(state.state);
    } else if (deviceType === 'fan') {
      setPower(state.state === 'on');
      setFanSpeed(attrs.percentage || 'off');
    } else if (deviceType === 'cover') {
      setPower(state.state === 'open');
      setCoverPosition(attrs.current_position || 0);
    } else if (deviceType === 'media_player') {
      setPower(state.state === 'playing');
    }
  }, [state.state, attrs.brightness, attrs.temperature, attrs.percentage, attrs.current_position, deviceType]);

  const sendCommand = useCallback(async (command, params = {}) => {
    setLoading(true);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/iot/devices/${device.id}/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command, ...params }),
      });
      return response.ok;
    } catch (error) {
      console.error('Error sending command:', error);
      return false;
    } finally {
      setLoading(false);
    }
  }, [device.id]);

  const handlePowerToggle = useCallback(async () => {
    const next = !power;
    setPower(next);
    const success = await sendCommand(next ? 'turn_on' : 'turn_off');
    if (!success) setPower(!next);
  }, [power, sendCommand]);

  const handleBrightnessChange = useCallback(async (value) => {
    const next = parseInt(value, 10);
    setBrightness(next);
    const success = await sendCommand('set_brightness', { params: { brightness: next } });
    if (!success) setBrightness(75);
  }, [sendCommand]);

  const handleTemperatureChange = useCallback(async (next) => {
    setTargetTemp(next);
    const success = await sendCommand('set_temperature', { params: { temperature: next } });
    if (!success) setTargetTemp(70);
  }, [sendCommand]);

  const handleLockToggle = useCallback(async () => {
    const next = lockState === 'locked' ? 'unlocked' : 'locked';
    setLockState(next);
    const success = await sendCommand(next === 'locked' ? 'lock' : 'unlock');
    if (!success) setLockState(lockState);
  }, [lockState, sendCommand]);

  const handleFanSpeedCycle = useCallback(async () => {
    const nextSpeed = FAN_SPEEDS[(FAN_SPEEDS.indexOf(fanSpeed) + 1) % FAN_SPEEDS.length];
    const prevSpeed = fanSpeed;
    setFanSpeed(nextSpeed);
    const success = await sendCommand('set_speed', { params: { speed: nextSpeed } });
    if (!success) setFanSpeed(prevSpeed);
  }, [fanSpeed, sendCommand]);

  const handleCoverPositionChange = useCallback(async (position) => {
    setCoverPosition(position);
    const success = await sendCommand('set_position', { params: { position } });
    if (!success) setCoverPosition(0);
  }, [sendCommand]);

  const handleMediaToggle = useCallback(async () => {
    const next = !power;
    setPower(next);
    const success = await sendCommand(next ? 'media_play' : 'media_pause');
    if (!success) setPower(!next);
  }, [power, sendCommand]);

  const disabled = !canControl || loading;

  const renderControl = () => {
    if (!device.online) {
      return (
        <div className="text-center text-fui-text/50 font-mono text-[10px] uppercase tracking-widest py-1">
          Offline
        </div>
      );
    }
    switch (deviceType) {
      case 'light':
        return (
          <div className="flex items-center gap-2">
            <ToggleSwitch on={power} onToggle={handlePowerToggle} disabled={disabled} />
            <input
              type="range"
              min="0"
              max="100"
              value={brightness}
              onChange={(e) => handleBrightnessChange(e.target.value)}
              disabled={disabled || !power}
              className="flex-1 accent-fui-accent h-1 disabled:opacity-40"
            />
          </div>
        );
      case 'climate':
      case 'thermostat':
        return (
          <div className="flex items-center justify-between gap-1">
            <ToggleSwitch on={power} onToggle={handlePowerToggle} disabled={disabled} />
            <div className="flex items-center gap-1">
              <button
                onClick={() => handleTemperatureChange(Math.max(50, targetTemp - 1))}
                disabled={disabled}
                className="w-5 h-5 border border-fui-border text-fui-text hover:border-fui-accent disabled:opacity-40"
              >
                -
              </button>
              <span className="text-fui-accent font-mono w-8 text-center">{targetTemp}°</span>
              <button
                onClick={() => handleTemperatureChange(Math.min(90, targetTemp + 1))}
                disabled={disabled}
                className="w-5 h-5 border border-fui-border text-fui-text hover:border-fui-accent disabled:opacity-40"
              >
                +
              </button>
            </div>
          </div>
        );
      case 'fan':
        return (
          <div className="flex items-center justify-between gap-2">
            <ToggleSwitch on={power} onToggle={handlePowerToggle} disabled={disabled} />
            <button
              onClick={handleFanSpeedCycle}
              disabled={disabled || !power}
              className="flex-1 py-1 border border-fui-border text-fui-text uppercase text-[10px] tracking-widest hover:border-fui-accent disabled:opacity-40"
            >
              {fanSpeed}
            </button>
          </div>
        );
      case 'cover':
        return (
          <div className="flex items-center gap-1">
            <button
              onClick={() => handleCoverPositionChange(0)}
              disabled={disabled}
              className="flex-1 py-1 border border-fui-border text-fui-text uppercase text-[10px] tracking-widest hover:border-fui-accent disabled:opacity-40"
            >
              Close
            </button>
            <span className="text-fui-accent font-mono text-[10px] w-8 text-center">{coverPosition}%</span>
            <button
              onClick={() => handleCoverPositionChange(100)}
              disabled={disabled}
              className="flex-1 py-1 border border-fui-border text-fui-text uppercase text-[10px] tracking-widest hover:border-fui-accent disabled:opacity-40"
            >
              Open
            </button>
          </div>
        );
      case 'lock':
        return (
          <button
            onClick={handleLockToggle}
            disabled={disabled}
            className={`w-full py-1 flex items-center justify-center gap-1 uppercase text-[10px] tracking-widest border disabled:opacity-40 ${
              lockState === 'locked'
                ? 'border-error text-error'
                : 'border-success text-success'
            }`}
          >
            {lockState === 'locked' ? <Lock className="w-3 h-3" /> : <Unlock className="w-3 h-3" />}
            {lockState === 'locked' ? 'Locked' : 'Unlocked'}
          </button>
        );
      case 'media_player':
        return (
          <button
            onClick={handleMediaToggle}
            disabled={disabled}
            className="w-full py-1 flex items-center justify-center gap-1 border border-fui-border text-fui-accent hover:border-fui-accent disabled:opacity-40"
          >
            {power ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
            {power ? 'Playing' : 'Paused'}
          </button>
        );
      case 'sensor':
      case 'binary_sensor':
        return (
          <div className="text-center text-fui-accent font-mono text-sm">
            {state.state !== undefined ? String(state.state) : '--'}
          </div>
        );
      default:
        return <ToggleSwitch on={power} onToggle={handlePowerToggle} disabled={disabled} />;
    }
  };

  return (
    <motion.div
      whileHover={{ scale: 1.02 }}
      className="relative border border-fui-border bg-fui-panel/60 p-2 flex flex-col gap-2 min-w-0"
    >
      {editMode && (
        <button
          onClick={() => onRemove(device.id)}
          className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-error text-white flex items-center justify-center z-10"
          title="Remove from quick controls"
        >
          <X className="w-3 h-3" />
        </button>
      )}
      <div className="flex items-center gap-1.5 min-w-0">
        <Icon className={`w-3.5 h-3.5 flex-shrink-0 ${device.online ? 'text-fui-accent' : 'text-fui-text'}`} />
        <span className="text-fui-text font-mono text-[11px] truncate flex-1" title={device.name}>
          {device.name}
        </span>
        {loading && <RefreshCw className="w-3 h-3 text-fui-accent animate-spin flex-shrink-0" />}
      </div>
      {renderControl()}
    </motion.div>
  );
};

const ToggleSwitch = ({ on, onToggle, disabled }) => (
  <motion.button
    whileTap={{ scale: 0.95 }}
    onClick={onToggle}
    disabled={disabled}
    className={`w-8 h-4 rounded-full p-0.5 transition-colors flex-shrink-0 ${
      on ? 'bg-fui-accent' : 'bg-fui-border'
    } ${disabled ? 'opacity-40 cursor-not-allowed' : ''}`}
  >
    <motion.div animate={{ x: on ? 16 : 0 }} className="w-3 h-3 rounded-full bg-black" />
  </motion.button>
);

ToggleSwitch.propTypes = {
  on: PropTypes.bool.isRequired,
  onToggle: PropTypes.func.isRequired,
  disabled: PropTypes.bool,
};

FavoriteDeviceTile.propTypes = {
  device: PropTypes.object.isRequired,
  canControl: PropTypes.bool,
  editMode: PropTypes.bool,
  onRemove: PropTypes.func,
};

export default FavoriteDeviceTile;
