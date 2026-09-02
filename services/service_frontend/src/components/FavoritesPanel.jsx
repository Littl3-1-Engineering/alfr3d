import { motion, AnimatePresence } from 'framer-motion';
import { X, Pencil, Star, Check } from 'lucide-react';
import { useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import { API_BASE_URL } from '../config';
import { apiFetch } from '../utils/apiClient';
import { useAuth } from '../utils/useAuth';
import socket from '../utils/socket';
import TacticalPanelVariant6 from './TacticalPanelVariant6';
import FavoriteDeviceTile from './FavoriteDeviceTile';
import ControlBlade from './ControlBlade';

const MAX_FAVORITES = 10;

// Top-center drop-down opened by clicking the Nexus Core -- the quick-access counterpart to the
// left/right CollapsibleSidePanel tabs (weather/clock/camera/project tree), but self-contained
// (positioning + content in one file, matching ControlBlade.jsx's precedent) since there's only
// one top-center consumer today.
const FavoritesPanel = ({ isOpen, onClose }) => {
  const { isAuthenticated } = useAuth();
  const [allDevices, setAllDevices] = useState([]);
  const [favorites, setFavorites] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [editMode, setEditMode] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [selectedDeviceAnchor, setSelectedDeviceAnchor] = useState(null);

  const handleDeviceSelect = (device, anchor) => {
    setSelectedDevice(device);
    setSelectedDeviceAnchor(anchor);
  };

  const closeControlBlade = () => {
    setSelectedDevice(null);
    setSelectedDeviceAnchor(null);
  };

  const fetchJson = (url) => apiFetch(url).then((r) => (r.ok ? r.json() : Promise.reject(r.status)));

  useEffect(() => {
    if (!isOpen || !isAuthenticated) return undefined;

    setLoading(true);
    setError(null);
    Promise.all([
      fetchJson(`${API_BASE_URL}/api/iot/devices`),
      fetchJson(`${API_BASE_URL}/api/iot/favorites`),
    ])
      .then(([devices, favs]) => {
        setAllDevices(devices);
        setFavorites(favs);
      })
      .catch(() => setError('Unable to load quick controls'))
      .finally(() => setLoading(false));

    const handleDevicesUpdate = (devices) => {
      setAllDevices(devices);
      const byId = new Map(devices.map((d) => [d.id, d]));
      setFavorites((prev) => prev.map((f) => byId.get(f.id) || f));
      setSelectedDevice((prev) => (prev ? byId.get(prev.id) || prev : prev));
    };
    socket.on('iot_devices', handleDevicesUpdate);
    return () => socket.off('iot_devices', handleDevicesUpdate);
  }, [isOpen, isAuthenticated]);

  const toggleFavorite = useCallback(async (deviceId, isFavorite) => {
    try {
      const response = isFavorite
        ? await apiFetch(`${API_BASE_URL}/api/iot/favorites/${deviceId}`, { method: 'DELETE' })
        : await apiFetch(`${API_BASE_URL}/api/iot/favorites`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: deviceId }),
          });
      if (response.ok) {
        setFavorites(await response.json());
      }
    } catch (err) {
      console.error('Error updating favorite device:', err);
    }
  }, []);

  const favoriteIds = new Set(favorites.map((f) => f.id));
  const atCap = favorites.length >= MAX_FAVORITES;

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0, y: -30 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -30 }}
          transition={{ duration: 0.3, ease: 'easeInOut' }}
          className="fixed top-20 left-1/2 -translate-x-1/2 z-40 w-fit max-w-[94vw]"
        >
          <TacticalPanelVariant6 title="Qu1ck C0ntr0ls">
            <div className="absolute -top-1 right-8 flex items-center gap-2 z-10">
              {isAuthenticated && (
                <button
                  onClick={() => setEditMode((v) => !v)}
                  className={`w-6 h-6 flex items-center justify-center border ${
                    editMode ? 'border-fui-accent text-fui-accent bg-fui-accent/10' : 'border-fui-border text-fui-text'
                  }`}
                  title={editMode ? 'Done editing' : 'Edit favorite devices'}
                >
                  {editMode ? <Check className="w-3.5 h-3.5" /> : <Pencil className="w-3.5 h-3.5" />}
                </button>
              )}
              <button
                onClick={onClose}
                className="w-6 h-6 flex items-center justify-center border border-fui-border text-fui-text hover:border-fui-accent"
                title="Close"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            {!isAuthenticated && (
              <p className="text-fui-text text-center py-6">Sign in to set up quick device controls.</p>
            )}

            {isAuthenticated && loading && (
              <p className="text-fui-accent text-center py-6 uppercase tracking-widest">Loading...</p>
            )}

            {isAuthenticated && error && (
              <p className="text-error text-center py-6">{error}</p>
            )}

            {isAuthenticated && !loading && !error && !editMode && (
              favorites.length > 0 ? (
                <div className="grid grid-cols-3 gap-2">
                  {favorites.map((device) => (
                    <FavoriteDeviceTile key={device.id} device={device} canControl onSelect={handleDeviceSelect} />
                  ))}
                </div>
              ) : (
                <div className="text-center py-6">
                  <p className="text-fui-text mb-3">No quick controls yet.</p>
                  <button
                    onClick={() => setEditMode(true)}
                    className="px-4 py-1.5 border border-fui-accent text-fui-accent uppercase text-[11px] tracking-widest hover:bg-fui-accent hover:text-black transition-colors"
                  >
                    Add Devices
                  </button>
                </div>
              )
            )}

            {isAuthenticated && !loading && !error && editMode && (
              <div className="max-h-64 overflow-y-auto flex flex-col gap-1">
                <p className="text-fui-text text-[10px] uppercase tracking-widest mb-1">
                  {favorites.length}/{MAX_FAVORITES} selected
                </p>
                {allDevices.length === 0 && (
                  <p className="text-fui-text text-center py-4">No smarthome devices found.</p>
                )}
                {allDevices.map((device) => {
                  const isFavorite = favoriteIds.has(device.id);
                  const disabled = !isFavorite && atCap;
                  return (
                    <button
                      key={device.id}
                      onClick={() => !disabled && toggleFavorite(device.id, isFavorite)}
                      disabled={disabled}
                      className={`flex items-center justify-between px-2 py-1.5 border text-left transition-colors ${
                        isFavorite ? 'border-fui-accent bg-fui-accent/10' : 'border-fui-border'
                      } ${disabled ? 'opacity-40 cursor-not-allowed' : 'hover:border-fui-accent'}`}
                    >
                      <span className="truncate">
                        {device.name}
                        <span className="text-fui-text ml-2">{device.room || device.device_type}</span>
                      </span>
                      <Star className={`w-3.5 h-3.5 flex-shrink-0 ${isFavorite ? 'text-fui-accent fill-fui-accent' : 'text-fui-text'}`} />
                    </button>
                  );
                })}
              </div>
            )}
          </TacticalPanelVariant6>

          <ControlBlade device={selectedDevice} anchor={selectedDeviceAnchor} onClose={closeControlBlade} />
        </motion.div>
      )}
    </AnimatePresence>
  );
};

FavoritesPanel.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
};

export default FavoritesPanel;
