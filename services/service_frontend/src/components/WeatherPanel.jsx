import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';
import socket from '../utils/socket';
import { formatTimeWithTimezone } from '../utils/timeUtils';

const WeatherPanel = ({ initialWeather = null, pollInterval = 600000 }) => {
  const [weatherData, setWeatherData] = useState(initialWeather || {});
  const [isLoading, setIsLoading] = useState(!initialWeather);
  const [error, setError] = useState(false);

  const fetchWeather = async () => {
    try {
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
    }
  };

  useEffect(() => {
    if (!initialWeather || Object.keys(weatherData).length === 0) {
      fetchWeather().finally(() => setIsLoading(false));
    }
    const weatherTimer = setInterval(fetchWeather, pollInterval);

    const handleWeatherUpdate = (data) => {
      setWeatherData(data);
      setIsLoading(false);
    };

    socket.on('weather', handleWeatherUpdate);

    return () => {
      clearInterval(weatherTimer);
      socket.off('weather', handleWeatherUpdate);
    };
  }, []);

  const formatTime = (isoString) => {
    return formatTimeWithTimezone(isoString, weatherData.timezone);
  };

  return (
    <div className="p-4 relative">
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
                 <span className="text-fui-text font-mono ml-1">{weatherData.pressure != null ? weatherData.pressure : 'N/A'} hPa</span>
               </div>
            </div>
          </div>
        )}
    </div>
  );
};

export default WeatherPanel;
