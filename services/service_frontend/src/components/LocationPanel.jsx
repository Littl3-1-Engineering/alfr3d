import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Circle } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { API_BASE_URL } from '../config';

const LocationPanel = () => {
  const [envData, setEnvData] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(false);

  // Custom crosshair icon
  const crosshairIcon = new L.DivIcon({
    html: `
      <div style="
        width: 20px;
        height: 20px;
        border: 2px solid #eab308;
        border-radius: 50%;
        position: relative;
      ">
        <div style="
          position: absolute;
          top: 50%;
          left: 0;
          right: 0;
          height: 2px;
          background: #eab308;
          transform: translateY(-50%);
        "></div>
        <div style="
          position: absolute;
          left: 50%;
          top: 0;
          bottom: 0;
          width: 2px;
          background: #eab308;
          transform: translateX(-50%);
        "></div>
      </div>
    `,
    className: 'custom-crosshair',
    iconSize: [20, 20],
    iconAnchor: [10, 10]
  });

  useEffect(() => {
    const fetchEnv = async () => {
      try {
        setIsLoading(true);
        setError(false);
        const response = await fetch(`${API_BASE_URL}/api/environment`);
        if (response.ok) {
          const data = await response.json();
          setEnvData(data);
        } else {
          setError(true);
        }
      } catch (error) {
        console.error('Failed to fetch environment:', error);
        setError(true);
      } finally {
        setIsLoading(false);
      }
    };

    fetchEnv();
    const envTimer = setInterval(fetchEnv, 60000);
    return () => clearInterval(envTimer);
  }, []);

  const abbreviateCity = (city) => {
    if (!city) return 'UNK';
    const words = city.split(' ');
    if (words.length > 1) {
      return words.map(w => w[0]).join('').toUpperCase();
    } else {
      return (city[0] + city[city.length - 1]).toUpperCase();
    }
  };

  const formatCoord = (coord) => {
    if (coord == null) return 'N/A';
    const abs = Math.abs(coord);
    const degrees = Math.floor(abs);
    const minutes = Math.floor((abs % 1) * 60);
    const seconds = Math.round(((abs % 1) * 60 % 1) * 60);
    return degrees + '°' + minutes + "'" + seconds + '"';
  };

  const cityAbbrev = abbreviateCity(envData.city);
  const latFormatted = formatCoord(envData.latitude);
  const longFormatted = formatCoord(envData.longitude);

  // Check if we have valid coordinates
  const hasValidCoords = envData.latitude != null && envData.longitude != null && !error;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6 }}
      className="relative bg-fui-panel border border-fui-border rounded-none"
    >
      {/* Corner Markers */}
      <div className="absolute -top-px -left-px w-3 h-3 border-t-2 border-l-2 border-fui-accent z-10" />
      <div className="absolute -top-px -right-px w-3 h-3 border-t-2 border-r-2 border-fui-accent z-10" />
      <div className="absolute -bottom-px -left-px w-3 h-3 border-b-2 border-l-2 border-fui-accent z-10" />
      <div className="absolute -bottom-px -right-px w-3 h-3 border-b-2 border-r-2 border-fui-accent z-10" />

      {/* Custom Folder Tab Header */}
      <div className="absolute top-0 right-0 border-l-4 border-fui-accent bg-black/60 px-2 py-1 z-20">
        <h3 className="font-tech text-lg text-white uppercase">
          LOCATION {cityAbbrev}-42
        </h3>
      </div>

      {/* Content Area */}
      <div className="p-4 relative pt-8">
        {/* Map Area */}
        {isLoading ? (
          <div className="min-h-[240px] bg-tech-grid bg-[length:20px_20px] relative flex items-center justify-center">
            <p className="text-fui-accent font-mono uppercase text-sm">LOCATING...</p>
          </div>
        ) : hasValidCoords ? (
          <MapContainer
            center={[envData.latitude, envData.longitude]}
            zoom={15}
            maxZoom={16}
            minZoom={14}
            style={{ height: 'auto', minHeight: '240px', width: '100%' }}
            className="rounded-none"
            zoomControl={false}
          >
            <TileLayer
              url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
            />
            <Marker position={[envData.latitude, envData.longitude]} icon={crosshairIcon} />
            <Circle
              center={[envData.latitude, envData.longitude]}
              radius={100}
              pathOptions={{
                color: '#eab308',
                fillColor: '#eab308',
                fillOpacity: 0.1,
                weight: 2
              }}
            />
          </MapContainer>
        ) : (
          <div className="min-h-[240px] bg-tech-grid bg-[length:20px_20px] relative flex items-center justify-center">
            <p className="text-red-400 font-mono uppercase text-sm">LOCATION UNAVAILABLE</p>
          </div>
        )}

        {/* Footer Data */}
        <div className="flex gap-4 mt-4">
          <div className="flex flex-col">
            <p className="text-xs text-fui-text/60 font-mono uppercase">PNT TRACK #1</p>
            <p className="text-lg font-mono text-fui-text">{latFormatted}</p>
          </div>
          <div className="flex flex-col">
            <p className="text-xs text-fui-text/60 font-mono uppercase">PNT TRACK #2</p>
            <p className="text-lg font-mono text-fui-text">{longFormatted}</p>
          </div>
        </div>
      </div>
    </motion.div>
  );
};

export default LocationPanel;
