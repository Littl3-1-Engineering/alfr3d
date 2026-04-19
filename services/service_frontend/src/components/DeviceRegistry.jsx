import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Monitor } from 'lucide-react';
import { API_BASE_URL } from '../config';

const USER_DEVICE_TYPES = ['HW', 'guest', 'resident'];

const EditableDeviceCard = ({ device, users, deviceTypes, onSave }) => {
  const [editDevice, setEditDevice] = useState({ ...device });
  const [isEditing, setIsEditing] = useState(false);

  const isUserDevice = device.user && device.user !== 'alfr3d';
  const availableTypes = isUserDevice
    ? deviceTypes.filter(t => USER_DEVICE_TYPES.includes(t.type)).map(t => t.type)
    : deviceTypes.filter(t => t.type !== 'guest' && t.type !== 'resident').map(t => t.type);

  const handleAssignmentChange = (e) => {
    const newUser = e.target.value;
    setEditDevice((prev) => ({ ...prev, user: newUser }));
  };

  const handleTypeChange = (e) => {
    setEditDevice((prev) => ({ ...prev, type: e.target.value }));
  };

  const handleSave = async () => {
    await onSave(editDevice);
    setIsEditing(false);
  };

  const handleCancel = () => {
    setEditDevice({ ...device });
    setIsEditing(false);
  };

  if (isEditing) {
    return (
      <div className="glass rounded-2xl p-4 border border-primary/50 bg-card/30">
        <div className="space-y-3">
          <div>
            <label className="text-xs text-text-tertiary block mb-1">Name</label>
            <input
              type="text"
              value={editDevice.name}
              onChange={(e) => setEditDevice((prev) => ({ ...prev, name: e.target.value }))}
              className="w-full p-2 bg-card rounded text-text-primary text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-text-tertiary block mb-1">Assigned To</label>
            <select
              value={editDevice.user || ''}
              onChange={handleAssignmentChange}
              className="w-full p-2 bg-card rounded text-text-primary text-sm"
            >
              <option value="">Unassigned</option>
              <option value="unknown">Unknown</option>
              <option value="alfr3d">ALFR3D</option>
              {users.map((user) => (
                <option key={user.id} value={user.username}>
                  {user.username}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-text-tertiary block mb-1">Type</label>
            <select
              value={editDevice.type}
              onChange={handleTypeChange}
              className="w-full p-2 bg-card rounded text-text-primary text-sm"
            >
              {availableTypes.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>
          <div className="flex space-x-2 pt-2">
            <button
              onClick={handleSave}
              className="flex-1 px-3 py-1.5 bg-success/20 border border-success rounded text-success text-sm hover:bg-success/30"
            >
              Save
            </button>
            <button
              onClick={handleCancel}
              className="flex-1 px-3 py-1.5 bg-border/20 border border-border rounded text-text-tertiary text-sm hover:bg-border/30"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="glass rounded-2xl p-4 border border-primary/30 bg-card/20 cursor-pointer hover:bg-card-hover/30 transition-colors"
      onClick={() => setIsEditing(true)}
    >
      <div className="flex items-center justify-between mb-3">
        <Monitor className="w-5 h-5 text-primary" />
      </div>
      <div>
        <h3 className="text-base font-semibold text-text-primary">{device.name}</h3>
        <p className="text-sm text-primary uppercase">{device.type}</p>
        <p className="text-xs text-text-tertiary">IP: {device.ip}</p>
        <p className="text-xs text-text-tertiary">MAC: {device.mac}</p>
        <p className="text-xs text-text-tertiary">
          Assigned: {device.user || 'None'}
        </p>
        <p className="text-xs text-text-tertiary">
          State:{' '}
          <span className={device.state === 'online' ? 'text-success' : ''}>
            {device.state}
          </span>
        </p>
      </div>
    </div>
  );
};

EditableDeviceCard.propTypes = {
  device: PropTypes.object.isRequired,
  users: PropTypes.array.isRequired,
  deviceTypes: PropTypes.array.isRequired,
  onSave: PropTypes.func.isRequired,
};

const DeviceRegistry = () => {
  const [devices, setDevices] = useState([]);
  const [users, setUsers] = useState([]);
  const [deviceTypes, setDeviceTypes] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const [devicesRes, usersRes, typesRes] = await Promise.all([
        fetch(API_BASE_URL + '/api/devices'),
        fetch(API_BASE_URL + '/api/users'),
        fetch(API_BASE_URL + '/api/device-types'),
      ]);

      const devicesData = await devicesRes.json();
      const usersData = await usersRes.json();
      const typesData = await typesRes.json();

      setDevices(devicesData);
      setUsers(usersData);
      setDeviceTypes(typesData);
    } catch (err) {
      console.error('Error fetching data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const userDevices = devices.filter((d) => d.user && d.user !== 'alfr3d' && d.user.toLowerCase() !== 'unknown');
  const alfr3dDevices = devices.filter((d) => d.user === 'alfr3d');
  const unassignedDevices = devices.filter((d) => !d.user || d.user.toLowerCase() === 'unknown');

  const handleDeviceSave = async (updatedDevice) => {
    try {
      let userValue = null;
      if (updatedDevice.user === 'alfr3d') {
        userValue = 'alfr3d';
      } else if (updatedDevice.user === 'unknown') {
        userValue = 'unknown';
      } else if (updatedDevice.user) {
        userValue = updatedDevice.user;
      }

      const payload = {
        name: updatedDevice.name,
        type: updatedDevice.type,
        user: userValue,
      };

      await fetch(`${API_BASE_URL}/api/devices/${updatedDevice.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      await fetchData();
    } catch (err) {
      console.error('Error updating device:', err);
    }
  };

  if (loading) {
    return (
      <div className="text-center py-8 text-fui-text font-mono">
        [ LOADING DEVICES... ]
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-xl font-bold text-fui-accent mb-4">USER DEVICES</h2>
        {userDevices.length === 0 ? (
          <p className="text-text-tertiary text-sm font-mono">
            [ NO USER DEVICES ASSIGNED ]
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {userDevices.map((device) => (
              <EditableDeviceCard
                key={device.id}
                device={device}
                users={users}
                deviceTypes={deviceTypes}
                onSave={handleDeviceSave}
              />
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-xl font-bold text-fui-accent mb-4">ALFR3D DEVICES</h2>
        {alfr3dDevices.length === 0 ? (
          <p className="text-text-tertiary text-sm font-mono">
            [ NO ALFR3D DEVICES ASSIGNED ]
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {alfr3dDevices.map((device) => (
              <EditableDeviceCard
                key={device.id}
                device={device}
                users={users}
                deviceTypes={deviceTypes}
                onSave={handleDeviceSave}
              />
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-xl font-bold text-fui-accent mb-4">UNASSIGNED DEVICES</h2>
        {unassignedDevices.length === 0 ? (
          <p className="text-text-tertiary text-sm font-mono">
            [ NO UNASSIGNED DEVICES ]
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {unassignedDevices.map((device) => (
              <EditableDeviceCard
                key={device.id}
                device={device}
                users={users}
                deviceTypes={deviceTypes}
                onSave={handleDeviceSave}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default DeviceRegistry;
