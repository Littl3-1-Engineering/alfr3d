import { useState, useEffect, useMemo } from 'react';
import { ArrowUp, ArrowDown, Minus } from 'lucide-react';
import PropTypes from 'prop-types';
import { API_BASE_URL } from '../config';
import socket from '../utils/socket';
import { formatTimeWithTimezone } from '../utils/timeUtils';
import WeatherIcon from './WeatherIcon';

const WeatherPanel = ({ initialWeather = null }) => {
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
    const handleWeatherUpdate = (data) => {
      setWeatherData(data);
      setIsLoading(false);
    };

    socket.on('weather', handleWeatherUpdate);

    return () => {
      socket.off('weather', handleWeatherUpdate);
    };
  }, []);

  const formatTime = (isoString) => {
    return formatTimeWithTimezone(isoString, weatherData.timezone);
  };

  const isNight = useMemo(() => {
    if (!weatherData.sunrise || !weatherData.sunset) return false;
    const now = Date.now();
    const sunrise = new Date(weatherData.sunrise).getTime();
    const sunset = new Date(weatherData.sunset).getTime();
    return now < sunrise || now > sunset;
  }, [weatherData.sunrise, weatherData.sunset]);

  const pressureTrend = weatherData.pressure_trend || 'steady';
  const TrendIcon = pressureTrend === 'rising'
    ? <ArrowUp size={12} className="inline text-success" />
    : pressureTrend === 'falling'
      ? <ArrowDown size={12} className="inline text-error" />
      : <Minus size={12} className="inline text-fui-text/60" />;

  const temperature = weatherData.temperature != null
    ? `${Math.round(weatherData.temperature)}°C`
    : 'N/A';

  const wind = weatherData.wind != null
    ? `${weatherData.wind} km/h ${weatherData.wind_dir || ''}`.trim()
    : 'N/A';

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
        <div className="space-y-3">
          {/* Temp + Icon */}
          <div className="flex items-center justify-center gap-4">
            <WeatherIcon description={weatherData.description} isNight={isNight} className="w-20 h-20" />
            <div>
              <div className="text-5xl font-exo2 font-bold text-fui-text leading-none">
                {temperature}
              </div>
              <div className="mt-1 text-xs font-mono text-fui-text/70 capitalize">
                {weatherData.description || 'N/A'}
              </div>
            </div>
          </div>

          {/* Wind + Pressure */}
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-fui-text/60 font-mono">WIND:</span>
              <span className="text-fui-text font-mono ml-1">{wind}</span>
            </div>
            <div>
              <span className="text-fui-text/60 font-mono">PRESSURE:</span>
              <span className="text-fui-text font-mono ml-1">
                {weatherData.pressure != null ? `${weatherData.pressure} hPa` : 'N/A'} {TrendIcon}
              </span>
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
          </div>
        </div>
      )}
    </div>
  );
};

WeatherPanel.propTypes = {
  initialWeather: PropTypes.object,
};

export default WeatherPanel;
