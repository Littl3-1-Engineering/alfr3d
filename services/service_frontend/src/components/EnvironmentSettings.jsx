import { useState, useEffect } from 'react';
import { Save, RotateCcw, ToggleLeft, ToggleRight } from 'lucide-react';
import { API_BASE_URL } from '../config';

const EnvironmentSettings = () => {
  const [environment, setEnvironment] = useState({
    city: '',
    state: '',
    country: '',
    latitude: '',
    longitude: '',
    temp_min: '',
    temp_max: '',
    pressure: '',
    humidity: '',
    manual_location_override: 0
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchEnvironment();
  }, []);

  const fetchEnvironment = async () => {
    try {
      const response = await fetch(API_BASE_URL + '/api/environment');
      const data = await response.json();
      setEnvironment(prev => ({ ...prev, ...data }));
    } catch (error) {
      console.error('Error fetching environment:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const dataToSend = {
        city: environment.city,
        state: environment.state,
        country: environment.country,
        latitude: environment.latitude,
        longitude: environment.longitude,
      };
      const response = await fetch(API_BASE_URL + '/api/environment', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dataToSend),
      });
      if (response.ok) {
        await fetchEnvironment();
      }
    } catch (error) {
      console.error('Error saving environment:', error);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (window.confirm('Reset to auto-detect environment? This will overwrite manual settings.')) {
      try {
        const response = await fetch(API_BASE_URL + '/api/environment/reset', {
          method: 'POST',
        });
        if (response.ok) {
          await fetchEnvironment();
        }
      } catch (error) {
        console.error('Error resetting environment:', error);
      }
    }
  };

  const handleToggleManual = () => {
    setEnvironment({ ...environment, manual_location_override: environment.manual_location_override ? 0 : 1 });
  };

  if (loading) {
    return (
      <div className="glass rounded-lg p-6 mb-8">
        <div className="animate-pulse">
          <div className="h-6 bg-card rounded mb-4"></div>
          <div className="h-4 bg-card rounded mb-2"></div>
          <div className="h-4 bg-card rounded"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="glass rounded-lg p-6 mb-8">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-primary">Environment Settings</h2>
        <div className="flex items-center space-x-4">
          <span className="text-sm text-text-tertiary">
            {environment.manual_location_override ? 'Manual' : 'Auto'}
          </span>
          <button
            onClick={handleToggleManual}
            className={`p-2 rounded-full transition-colors ${
              environment.manual_location_override
                ? 'bg-primary/20 text-primary'
                : 'bg-border-secondary/20 text-text-tertiary'
            }`}
          >
            {environment.manual_location_override ? (
              <ToggleRight className="w-6 h-6" />
            ) : (
              <ToggleLeft className="w-6 h-6" />
            )}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        <div>
          <label className="block text-sm font-medium text-text-secondary mb-1">City</label>
          <input
            type="text"
            value={environment.city}
            onChange={(e) => setEnvironment({ ...environment, city: e.target.value })}
            disabled={!environment.manual_location_override}
            className="w-full p-2 bg-card rounded text-text-primary disabled:opacity-50"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-text-secondary mb-1">State</label>
          <input
            type="text"
            value={environment.state}
            onChange={(e) => setEnvironment({ ...environment, state: e.target.value })}
            disabled={!environment.manual_location_override}
            className="w-full p-2 bg-card rounded text-text-primary disabled:opacity-50"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-text-secondary mb-1">Country</label>
          <input
            type="text"
            value={environment.country}
            onChange={(e) => setEnvironment({ ...environment, country: e.target.value })}
            disabled={!environment.manual_location_override}
            className="w-full p-2 bg-card rounded text-text-primary disabled:opacity-50"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-text-secondary mb-1">Latitude</label>
          <input
            type="number"
            step="0.0001"
            value={environment.latitude}
            onChange={(e) => setEnvironment({ ...environment, latitude: e.target.value })}
            disabled={!environment.manual_location_override}
            className="w-full p-2 bg-card rounded text-text-primary disabled:opacity-50"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-text-secondary mb-1">Longitude</label>
          <input
            type="number"
            step="0.0001"
            value={environment.longitude}
            onChange={(e) => setEnvironment({ ...environment, longitude: e.target.value })}
            disabled={!environment.manual_location_override}
            className="w-full p-2 bg-card rounded text-text-primary disabled:opacity-50"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-text-secondary mb-1">Min Temp (°C)</label>
          <input
            type="number"
            step="0.1"
            value={environment.temp_min}
            disabled={true}
            className="w-full p-2 bg-card rounded text-text-primary disabled:opacity-50"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-text-secondary mb-1">Max Temp (°C)</label>
          <input
            type="number"
            step="0.1"
            value={environment.temp_max}
            disabled={true}
            className="w-full p-2 bg-card rounded text-text-primary disabled:opacity-50"
          />
        </div>
         <div>
           <label className="block text-sm font-medium text-text-secondary mb-1">Pressure (hPa)</label>
           <input
             type="number"
             step="0.1"
             value={environment.pressure}
             disabled={true}
             className="w-full p-2 bg-card rounded text-text-primary disabled:opacity-50"
           />
         </div>
         <div>
           <label className="block text-sm font-medium text-text-secondary mb-1">Humidity (%)</label>
           <input
             type="number"
             step="0.1"
             value={environment.humidity}
             disabled={true}
             className="w-full p-2 bg-card rounded text-text-primary disabled:opacity-50"
           />
         </div>
       </div>

       <div className="flex space-x-4">
        <button
          onClick={handleSave}
          disabled={!environment.manual_location_override || saving}
          className="flex items-center space-x-2 px-4 py-2 bg-success/20 border border-success rounded-lg text-success hover:bg-success/30 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Save className="w-4 h-4" />
          <span>{saving ? 'Saving...' : 'Save'}</span>
        </button>
        <button
          onClick={handleReset}
          className="flex items-center space-x-2 px-4 py-2 bg-warning/20 border border-warning rounded-lg text-warning hover:bg-warning/30"
        >
          <RotateCcw className="w-4 h-4" />
          <span>Reset to Auto</span>
        </button>
      </div>
    </div>
  );
};

export default EnvironmentSettings;