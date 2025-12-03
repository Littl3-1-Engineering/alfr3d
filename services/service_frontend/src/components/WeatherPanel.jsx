import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';

const WeatherPanel = () => {
  const [weatherData, setWeatherData] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    const fetchWeather = async () => {
      try {
        setIsLoading(true);
        setError(false);
        const response = await fetch(`${API_BASE_URL}/api/weather`);
        if (response.ok) {
          const data = await response.json();
          setWeatherData(data);
        } else {
          setError(true);
        }
      } catch (error) {
        console.error('Failed to fetch weather:', error);
        setError(true);
      } finally {
        setIsLoading(false);
      }
    };

    fetchWeather();
    const weatherTimer = setInterval(fetchWeather, 600000); // Update every 10 minutes
    return () => clearInterval(weatherTimer);
  }, []);

  const formatTime = (isoString) => {
    if (!isoString) return 'N/A';
    const date = new Date(isoString);
    return date.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit'
    });
  };

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
          WEATHER
        </h3>
      </div>

      {/* Content Area */}
      <div className="p-4 relative pt-8">
        {isLoading ? (
          <div className="text-center">
            <p className="text-fui-accent font-mono uppercase text-sm">LOADING WEATHER...</p>
          </div>
        ) : error ? (
          <div className="text-center">
            <p className="text-red-400 font-mono uppercase text-sm">WEATHER UNAVAILABLE</p>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="text-center">
              <div className="text-lg font-mono text-fui-accent capitalize">
                {weatherData.description || 'N/A'}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <span className="text-fui-text/60 font-mono">LOW:</span>
                <span className="text-fui-text font-mono ml-1">{weatherData.low || 'N/A'}°C</span>
              </div>
              <div>
                <span className="text-fui-text/60 font-mono">HIGH:</span>
                <span className="text-fui-text font-mono ml-1">{weatherData.high || 'N/A'}°C</span>
              </div>
              <div>
                <span className="text-fui-text/60 font-mono">SUNRISE:</span>
                <span className="text-fui-text font-mono ml-1">{formatTime(weatherData.sunrise)}</span>
              </div>
              <div>
                <span className="text-fui-text/60 font-mono">SUNSET:</span>
                <span className="text-fui-text font-mono ml-1">{formatTime(weatherData.sunset)}</span>
              </div>
              <div>
                <span className="text-fui-text/60 font-mono">HUMIDITY:</span>
                <span className="text-fui-text font-mono ml-1">{weatherData.humidity || 'N/A'}%</span>
              </div>
              <div>
                <span className="text-fui-text/60 font-mono">PRESSURE:</span>
                <span className="text-fui-text font-mono ml-1">{weatherData.pressure || 'N/A'} hPa</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
};

export default WeatherPanel;
