import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { useNavigate } from 'react-router-dom';
import { User, Monitor, Plus } from 'lucide-react';
import { API_BASE_URL } from '../config';
import UserModal from './UserModal';
import DeviceHistoryModal from './DeviceHistoryModal';

const UserCard = ({ user, onClick }) => (
  <div
    className="glass rounded-2xl p-6 border border-primary/30 bg-card/20 cursor-pointer hover:bg-card-hover/30 transition-colors"
    onClick={() => onClick(user)}
  >
    <div className="flex items-center justify-between mb-4">
      <User className={'w-6 h-6 ' + (user.type !== 'guest' ? 'text-success' : 'text-warning')} />
    </div>
    <div>
      <h3 className="text-lg font-semibold text-text-primary">{user.name}</h3>
      <p className="text-sm text-primary uppercase">{user.type}</p>
      <p className="text-xs text-text-tertiary">{user.email}</p>
      <p className="text-xs text-text-tertiary">{user.about_me}</p>
      <p className="text-xs text-text-tertiary">Last Online: {user.last_online || 'Never'}</p>
      <p className="text-xs text-text-tertiary">State: <span className={user.state === 'online' ? 'text-success' : ''}>{user.state}</span></p>
    </div>
  </div>
);

UserCard.propTypes = {
  user: PropTypes.object.isRequired,
  onClick: PropTypes.func.isRequired,
};

const DeviceCard = ({ device, onClick }) => (
  <div
    className="glass rounded-2xl p-6 border border-primary/30 bg-card/20 cursor-pointer hover:bg-card-hover/30 transition-colors"
    onClick={() => onClick(device)}
  >
    <div className="flex items-center justify-between mb-4">
      <Monitor className="w-6 h-6 text-primary" />
    </div>
    <div>
      <h3 className="text-lg font-semibold text-text-primary">{device.name}</h3>
      <p className="text-sm text-primary uppercase">{device.type}</p>
      <p className="text-xs text-text-tertiary">IP: {device.ip}</p>
      <p className="text-xs text-text-tertiary">MAC: {device.mac}</p>
      <p className="text-xs text-text-tertiary">Last Online: {device.last_online || 'Never'}</p>
      <p className="text-xs text-text-tertiary">User: {device.user || 'None'}</p>
      <p className="text-xs text-text-tertiary">State: <span className={device.state === 'online' ? 'text-success' : ''}>{device.state}</span></p>
    </div>
  </div>
);

DeviceCard.propTypes = {
  device: PropTypes.object.isRequired,
  onClick: PropTypes.func.isRequired,
};

const PersonnelRoster = ({ initialUserId }) => {
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [devices, setDevices] = useState([]);
  const [newUser, setNewUser] = useState({ name: '', type: 'guest', email: '', about_me: '' });
  const [newDevice, setNewDevice] = useState({ name: '', type: 'guest', ip: '', mac: '', user: '' });
  const [showAddUser, setShowAddUser] = useState(false);
  const [showAddDevice, setShowAddDevice] = useState(false);
  const [showUserModal, setShowUserModal] = useState(false);
  const [showDeviceModal, setShowDeviceModal] = useState(false);
  const [modalUser, setModalUser] = useState(null);
  const [modalDevice, setModalDevice] = useState(null);
  const [userDevices, setUserDevices] = useState([]);
  const [deviceHistory, setDeviceHistory] = useState([]);

  useEffect(() => {
    fetch(API_BASE_URL + '/api/users-with-devices')
      .then(res => res.json())
      .then(data => {
        setUsers(data);
        const allDevices = data.flatMap(u => (u.devices || []).map(d => ({ ...d, user: u.name })));
        setDevices(allDevices);
      })
      .catch(err => console.error('Error fetching users with devices:', err));
  }, []);

  useEffect(() => {
    if (initialUserId && users.length > 0) {
      const user = users.find(u => u.id.toString() === initialUserId.toString());
      if (user) {
        setModalUser(user);
        setUserDevices(user.devices || []);
        setShowUserModal(true);
      } else {
        console.error('User not found');
        navigate('/');
      }
    }
  }, [initialUserId, users, navigate]);

  const handleUserClick = (user) => {
    setModalUser(user);
    setUserDevices(user.devices || []);
    setShowUserModal(true);
  };

  const handleDeviceHistoryClick = (device) => {
    setModalDevice(device);
    setDeviceHistory([]);
    setShowDeviceModal(true);
    fetch(API_BASE_URL + '/api/devices/' + device.id + '/history')
      .then(res => res.json())
      .then(history => setDeviceHistory(history))
      .catch(err => console.error('Error fetching device history:', err));
  };

  const closeUserModal = () => {
    setShowUserModal(false);
    setModalUser(null);
    setUserDevices([]);
  };

  const closeDeviceModal = () => {
    setShowDeviceModal(false);
    setModalDevice(null);
    setDeviceHistory([]);
  };

  const handleAddUser = () => {
    if (!newUser.name || !newUser.type) return;
    fetch(API_BASE_URL + '/api/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newUser),
    })
      .then(res => {
        if (res.ok) {
          return fetch(API_BASE_URL + '/api/users-with-devices');
        }
      })
      .then(res => res.json())
      .then(data => {
        setUsers(data);
        const allDevices = data.flatMap(u => (u.devices || []).map(d => ({ ...d, user: u.name })));
        setDevices(allDevices);
        setNewUser({ name: '', type: 'guest', email: '', about_me: '' });
        setShowAddUser(false);
      })
      .catch(err => console.error('Error adding user:', err));
  };

  const handleAddDevice = () => {
    if (!newDevice.name || !newDevice.type) return;
    fetch(API_BASE_URL + '/api/devices', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newDevice),
    })
      .then(res => {
        if (res.ok) {
          return fetch(API_BASE_URL + '/api/users-with-devices');
        }
      })
      .then(res => res.json())
      .then(data => {
        setUsers(data);
        const allDevices = data.flatMap(u => (u.devices || []).map(d => ({ ...d, user: u.name })));
        setDevices(allDevices);
        setNewDevice({ name: '', type: 'guest', ip: '', mac: '', user: '' });
        setShowAddDevice(false);
      })
      .catch(err => console.error('Error adding device:', err));
  };

  const handleModalSaveUser = (updatedUser) => {
    fetch(API_BASE_URL + '/api/users/' + updatedUser.id, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updatedUser),
    })
      .then(res => {
        if (res.ok) {
          return fetch(API_BASE_URL + '/api/users-with-devices');
        }
      })
      .then(res => res.json())
      .then(data => {
        setUsers(data);
        const allDevices = data.flatMap(u => (u.devices || []).map(d => ({ ...d, user: u.name })));
        setDevices(allDevices);
        setModalUser(updatedUser);
      })
      .catch(err => console.error('Error updating user:', err));
  };

  const handleDeleteUser = (id) => {
    if (window.confirm('Are you sure you want to delete this user?')) {
      fetch(API_BASE_URL + '/api/users/' + id, { method: 'DELETE' })
        .then(res => {
          if (res.ok) {
            return fetch(API_BASE_URL + '/api/users-with-devices');
          }
        })
        .then(res => res.json())
        .then(data => {
          setUsers(data);
          const allDevices = data.flatMap(u => (u.devices || []).map(d => ({ ...d, user: u.name })));
          setDevices(allDevices);
          closeUserModal();
        })
        .catch(err => console.error('Error deleting user:', err));
    }
  };

  const handleModalSaveDevice = (updatedDevice) => {
    fetch(API_BASE_URL + '/api/devices/' + updatedDevice.id, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updatedDevice),
    })
      .then(res => {
        if (res.ok) {
          return fetch(API_BASE_URL + '/api/users-with-devices');
        }
      })
      .then(res => res.json())
      .then(data => {
        setUsers(data);
        const allDevices = data.flatMap(u => (u.devices || []).map(d => ({ ...d, user: u.name })));
        setDevices(allDevices);
        setModalDevice(updatedDevice);
      })
      .catch(err => console.error('Error updating device:', err));
  };

  const handleDeleteDevice = (id) => {
    if (window.confirm('Are you sure you want to delete this device?')) {
      fetch(API_BASE_URL + '/api/devices/' + id, { method: 'DELETE' })
        .then(res => {
          if (res.ok) {
            return fetch(API_BASE_URL + '/api/users-with-devices');
          }
        })
        .then(res => res.json())
        .then(data => {
          setUsers(data);
          const allDevices = data.flatMap(u => (u.devices || []).map(d => ({ ...d, user: u.name })));
          setDevices(allDevices);
          closeDeviceModal();
        })
        .catch(err => console.error('Error deleting device:', err));
    }
  };

  PersonnelRoster.propTypes = {
    initialUserId: PropTypes.string
  };

  return (
    <div className="space-y-8">
      <div>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-2xl font-bold text-primary">Users</h2>
          <button
            onClick={() => setShowAddUser(true)}
            className="flex items-center space-x-2 px-4 py-2 bg-primary/20 border border-primary rounded-lg text-primary hover:bg-primary/30"
          >
            <Plus className="w-4 h-4" />
            <span>Add User</span>
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {users.map((user) => (
            <UserCard key={user.id} user={user} onClick={handleUserClick} />
          ))}
        </div>
        {showAddUser && (
          <div className="mt-4 glass rounded-2xl p-6 border border-primary/30 bg-card/20">
            <h3 className="text-lg font-semibold text-primary mb-4">Add New User</h3>
            <div className="space-y-3">
              <input
                value={newUser.name}
                onChange={(e) => setNewUser(prev => ({ ...prev, name: e.target.value }))}
                className="w-full p-2 bg-card rounded text-text-primary"
                placeholder="Name"
              />
              <select
                value={newUser.type}
                onChange={(e) => setNewUser(prev => ({ ...prev, type: e.target.value }))}
                className="w-full p-2 bg-card rounded text-text-primary"
              >
                <option value="technoking">Technoking</option>
                <option value="resident">Resident</option>
                <option value="guest">Guest</option>
              </select>
              <input
                value={newUser.email}
                onChange={(e) => setNewUser(prev => ({ ...prev, email: e.target.value }))}
                className="w-full p-2 bg-card rounded text-text-primary"
                placeholder="Email"
              />
              <textarea
                value={newUser.about_me}
                onChange={(e) => setNewUser(prev => ({ ...prev, about_me: e.target.value }))}
                className="w-full p-2 bg-card rounded text-text-primary"
                rows={2}
                placeholder="About Me"
              />
              <div className="flex space-x-2">
                <button
                  onClick={handleAddUser}
                  className="px-4 py-2 bg-success/20 border border-success rounded text-success hover:bg-success/30"
                >
                  Add
                </button>
                <button
                  onClick={() => setShowAddUser(false)}
                  className="px-4 py-2 bg-border/20 border border-border rounded text-text-tertiary hover:bg-border/30"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      <div>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-2xl font-bold text-primary">Devices</h2>
          <button
            onClick={() => setShowAddDevice(true)}
            className="flex items-center space-x-2 px-4 py-2 bg-primary/20 border border-primary rounded-lg text-primary hover:bg-primary/30"
          >
            <Plus className="w-4 h-4" />
            <span>Add Device</span>
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {devices.map((device) => (
            <DeviceCard key={device.id} device={device} onClick={handleDeviceHistoryClick} />
          ))}
        </div>
        {showAddDevice && (
          <div className="mt-4 glass rounded-2xl p-6 border border-primary/30 bg-card/20">
            <h3 className="text-lg font-semibold text-primary mb-4">Add New Device</h3>
            <div className="space-y-3">
              <input
                value={newDevice.name}
                onChange={(e) => setNewDevice(prev => ({ ...prev, name: e.target.value }))}
                className="w-full p-2 bg-card rounded text-text-primary"
                placeholder="Name"
              />
              <select
                value={newDevice.type}
                onChange={(e) => setNewDevice(prev => ({ ...prev, type: e.target.value }))}
                className="w-full p-2 bg-card rounded text-text-primary"
              >
                <option value="alfr3d">Alfr3d</option>
                <option value="HW">HW</option>
                <option value="guest">Guest</option>
                <option value="light">Light</option>
                <option value="resident">Resident</option>
              </select>
              <input
                value={newDevice.ip}
                onChange={(e) => setNewDevice(prev => ({ ...prev, ip: e.target.value }))}
                className="w-full p-2 bg-card rounded text-text-primary"
                placeholder="IP"
              />
              <input
                value={newDevice.mac}
                onChange={(e) => setNewDevice(prev => ({ ...prev, mac: e.target.value }))}
                className="w-full p-2 bg-card rounded text-text-primary"
                placeholder="MAC"
              />
              <select
                value={newDevice.user}
                onChange={(e) => setNewDevice(prev => ({ ...prev, user: e.target.value }))}
                className="w-full p-2 bg-card rounded text-text-primary"
              >
                <option value="">No User</option>
                {users.map(user => (
                  <option key={user.id} value={user.name}>{user.name}</option>
                ))}
              </select>
              <div className="flex space-x-2">
                <button
                  onClick={handleAddDevice}
                  className="px-4 py-2 bg-success/20 border border-success rounded text-success hover:bg-success/30"
                >
                  Add
                </button>
                <button
                  onClick={() => setShowAddDevice(false)}
                  className="px-4 py-2 bg-border/20 border border-border rounded text-text-tertiary hover:bg-border/30"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      <UserModal
        isOpen={showUserModal}
        onClose={closeUserModal}
        user={modalUser}
        devices={userDevices}
        onDeviceClick={handleDeviceHistoryClick}
        onSave={handleModalSaveUser}
        onDelete={handleDeleteUser}
      />

      <DeviceHistoryModal
        isOpen={showDeviceModal}
        onClose={closeDeviceModal}
        device={modalDevice}
        history={deviceHistory}
        users={users}
        onSave={handleModalSaveDevice}
        onDelete={handleDeleteDevice}
      />
    </div>
  );
};

export default PersonnelRoster;
