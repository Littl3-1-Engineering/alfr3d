import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import { User, Monitor, Edit, Trash2, Plus, Save, X } from 'lucide-react';
import { API_BASE_URL } from '../config';
import UserModal from './UserModal';
import DeviceHistoryModal from './DeviceHistoryModal';

const PersonnelRoster = () => {
  const [users, setUsers] = useState([]);
  const [devices, setDevices] = useState([]);
  const [editingUser, setEditingUser] = useState(null);
  const [editingDevice, setEditingDevice] = useState(null);
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
    console.log('PersonnelRoster component mounted');
    fetchUsers();
    fetchDevices();
  }, []);

  const fetchUsers = async () => {
    try {
      const response = await fetch(API_BASE_URL + '/api/users');
      const data = await response.json();
      setUsers(data);
    } catch (error) {
      console.error('Error fetching users:', error);
    }
  };

  const fetchDevices = async () => {
    try {
      const response = await fetch(API_BASE_URL + '/api/devices');
      const data = await response.json();
      setDevices(data);
    } catch (error) {
      console.error('Error fetching devices:', error);
    }
  };

  const handleEditUser = (user) => {
    setEditingUser({ ...user });
  };

  const handleSaveUser = async () => {
    try {
      const response = await fetch(API_BASE_URL + '/api/users/' + editingUser.id, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editingUser),
      });
      if (response.ok) {
        await fetchUsers();
        setEditingUser(null);
      }
    } catch (error) {
      console.error('Error updating user:', error);
    }
  };

  const handleDeleteUser = async (id) => {
    if (window.confirm('Are you sure you want to delete this user?')) {
      try {
        const response = await fetch(API_BASE_URL + '/api/users/' + id, {
          method: 'DELETE',
        });
        if (response.ok) {
          await fetchUsers();
        }
      } catch (error) {
        console.error('Error deleting user:', error);
      }
    }
  };

  const handleAddUser = async () => {
    if (!newUser.name || !newUser.type) return;
    try {
      const response = await fetch(API_BASE_URL + '/api/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newUser),
      });
      if (response.ok) {
        await fetchUsers();
        setNewUser({ name: '', type: 'guest', email: '', about_me: '' });
        setShowAddUser(false);
      }
    } catch (error) {
      console.error('Error adding user:', error);
    }
  };

  const handleEditDevice = (device) => {
    setEditingDevice({ ...device });
  };

  const handleSaveDevice = async () => {
    try {
      const response = await fetch(API_BASE_URL + '/api/devices/' + editingDevice.id, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editingDevice),
      });
      if (response.ok) {
        await fetchDevices();
        setEditingDevice(null);
      }
    } catch (error) {
      console.error('Error updating device:', error);
    }
  };

  const handleDeleteDevice = async (id) => {
    if (window.confirm('Are you sure you want to delete this device?')) {
      try {
        const response = await fetch(API_BASE_URL + '/api/devices/' + id, {
          method: 'DELETE',
        });
        if (response.ok) {
          await fetchDevices();
        }
      } catch (error) {
        console.error('Error deleting device:', error);
      }
    }
  };

  const handleAddDevice = async () => {
    if (!newDevice.name || !newDevice.type) return;
    try {
      const response = await fetch(API_BASE_URL + '/api/devices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newDevice),
      });
      if (response.ok) {
        await fetchDevices();
        setNewDevice({ name: '', type: 'guest', ip: '', mac: '', user: '' });
        setShowAddDevice(false);
      }
    } catch (error) {
      console.error('Error adding device:', error);
    }
  };

  const handleUserClick = async (user) => {
    console.log('handleUserClick called with user:', user);
    setModalUser(user);
    setUserDevices([]);
    setShowUserModal(true);
    console.log('Opening user modal for:', user);
    try {
      const response = await fetch(API_BASE_URL + '/api/users/' + user.id + '/devices');
      const devices = await response.json();
      console.log('Received devices:', devices);
      setUserDevices(devices);
      console.log('User modal opened with devices');
    } catch (error) {
      console.error('Error fetching user devices:', error);
    }
  };

  const handleDeviceHistoryClick = async (device) => {
    console.log('handleDeviceHistoryClick called with device:', device);
    setModalDevice(device);
    setDeviceHistory([]);
    setShowDeviceModal(true);
    console.log('Opening device history modal for:', device);
    try {
      const response = await fetch(API_BASE_URL + '/api/devices/' + device.id + '/history');
      const history = await response.json();
      console.log('Received history:', history);
      setDeviceHistory(history);
      console.log('Device history modal opened');
    } catch (error) {
      console.error('Error fetching device history:', error);
    }
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

  console.log('Rendering PersonnelRoster with modals:', { showUserModal, showDeviceModal, userDevices: userDevices.length, deviceHistory: deviceHistory.length });

  return (
    <div className="space-y-8">
      {/* Users Section */}
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
          {users.map((user, index) => (
            <motion.div
              key={user.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1, duration: 0.5 }}
              className="glass rounded-2xl p-6 border border-primary/30 bg-card/20 cursor-pointer hover:bg-card-hover/30 transition-colors"
              onClick={() => {
                console.log('User card clicked!');
                handleUserClick(user);
              }}
            >
              <div className="flex items-center justify-between mb-4">
                  <User className={'w-6 h-6 ' + (user.type !== 'guest' ? 'text-success' : 'text-warning')} />
                <div className="flex space-x-2">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleEditUser(user);
                    }}
                    className="p-1 text-primary hover:bg-primary/20 rounded"
                  >
                    <Edit className="w-4 h-4" />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteUser(user.id);
                    }}
                    className="p-1 text-error hover:bg-error/20 rounded"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              {editingUser && editingUser.id === user.id ? (
                <div className="space-y-2">
                  <input
                    value={editingUser.name}
                    onChange={(e) => setEditingUser({ ...editingUser, name: e.target.value })}
                    className="w-full p-2 bg-card rounded text-text-primary"
                    placeholder="Name"
                  />
                  <select
                    value={editingUser.type}
                    onChange={(e) => setEditingUser({ ...editingUser, type: e.target.value })}
                    className="w-full p-2 bg-card rounded text-text-primary"
                  >
                    <option value="technoking">Technoking</option>
                    <option value="resident">Resident</option>
                    <option value="guest">Guest</option>
                  </select>
                  <input
                    value={editingUser.email}
                    onChange={(e) => setEditingUser({ ...editingUser, email: e.target.value })}
                    className="w-full p-2 bg-card rounded text-text-primary"
                    placeholder="Email"
                  />
                  <textarea
                    value={editingUser.about_me}
                    onChange={(e) => setEditingUser({ ...editingUser, about_me: e.target.value })}
                    className="w-full p-2 bg-card rounded text-text-primary"
                    rows={2}
                    placeholder="About Me"
                  />
                  <div className="flex space-x-2">
                    <button
                      onClick={handleSaveUser}
                      className="px-3 py-1 bg-success/20 border border-success rounded text-success hover:bg-success/30"
                    >
                      <Save className="w-4 h-4 inline mr-1" />
                      Save
                    </button>
                    <button
                      onClick={() => setEditingUser(null)}
                      className="px-3 py-1 bg-border/20 border border-border rounded text-text-tertiary hover:bg-border/30"
                    >
                      <X className="w-4 h-4 inline mr-1" />
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div>
                  <h3 className="text-lg font-semibold text-text-primary">{user.name}</h3>
                  <p className="text-sm text-primary uppercase">{user.type}</p>
                  <p className="text-xs text-text-tertiary">{user.email}</p>
                  <p className="text-xs text-text-tertiary">{user.about_me}</p>
                  <p className="text-xs text-text-tertiary">State: {user.state}</p>
                </div>
              )}
            </motion.div>
          ))}
        </div>
        {showAddUser && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="mt-4 glass rounded-2xl p-6 border border-primary/30 bg-card/20"
          >
            <h3 className="text-lg font-semibold text-primary mb-4">Add New User</h3>
            <div className="space-y-3">
              <input
                value={newUser.name}
                onChange={(e) => setNewUser({ ...newUser, name: e.target.value })}
                className="w-full p-2 bg-card rounded text-text-primary"
                placeholder="Name"
              />
              <select
                value={newUser.type}
                onChange={(e) => setNewUser({ ...newUser, type: e.target.value })}
                className="w-full p-2 bg-card rounded text-text-primary"
              >
                <option value="technoking">Technoking</option>
                <option value="resident">Resident</option>
                <option value="guest">Guest</option>
              </select>
              <input
                value={newUser.email}
                onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
                className="w-full p-2 bg-card rounded text-text-primary"
                placeholder="Email"
              />
              <textarea
                value={newUser.about_me}
                onChange={(e) => setNewUser({ ...newUser, about_me: e.target.value })}
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
          </motion.div>
        )}
      </div>

      {/* Devices Section */}
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
          {devices.map((device, index) => (
            <motion.div
              key={device.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1, duration: 0.5 }}
              className="glass rounded-2xl p-6 border border-primary/30 bg-card/20 cursor-pointer hover:bg-card-hover/30 transition-colors"
                  onClick={() => {
                    console.log('User device card clicked!');
                    handleDeviceHistoryClick(device);
                  }}
            >
              <div className="flex items-center justify-between mb-4">
                <Monitor className="w-6 h-6 text-primary" />
                <div className="flex space-x-2">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleEditDevice(device);
                    }}
                    className="p-1 text-primary hover:bg-primary/20 rounded"
                  >
                    <Edit className="w-4 h-4" />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteDevice(device.id);
                    }}
                    className="p-1 text-error hover:bg-error/20 rounded"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              {editingDevice && editingDevice.id === device.id ? (
                <div className="space-y-2">
                  <input
                    value={editingDevice.name}
                    onChange={(e) => setEditingDevice({ ...editingDevice, name: e.target.value })}
                    className="w-full p-2 bg-card rounded text-text-primary"
                    placeholder="Name"
                  />
                  <select
                    value={editingDevice.type}
                    onChange={(e) => setEditingDevice({ ...editingDevice, type: e.target.value })}
                    className="w-full p-2 bg-card rounded text-text-primary"
                  >
                    <option value="alfr3d">Alfr3d</option>
                    <option value="HW">HW</option>
                    <option value="guest">Guest</option>
                    <option value="light">Light</option>
                    <option value="resident">Resident</option>
                  </select>
                  <input
                    value={editingDevice.ip}
                    onChange={(e) => setEditingDevice({ ...editingDevice, ip: e.target.value })}
                    className="w-full p-2 bg-card rounded text-text-primary"
                    placeholder="IP"
                  />
                  <input
                    value={editingDevice.mac}
                    onChange={(e) => setEditingDevice({ ...editingDevice, mac: e.target.value })}
                    className="w-full p-2 bg-card rounded text-text-primary"
                    placeholder="MAC"
                  />
                  <select
                    value={editingDevice.user || ''}
                    onChange={(e) => setEditingDevice({ ...editingDevice, user: e.target.value })}
                    className="w-full p-2 bg-card rounded text-text-primary"
                  >
                    <option value="">No User</option>
                    {users.map(user => (
                      <option key={user.id} value={user.name}>{user.name}</option>
                    ))}
                  </select>
                  <div className="flex space-x-2">
                    <button
                      onClick={handleSaveDevice}
                      className="px-3 py-1 bg-success/20 border border-success rounded text-success hover:bg-success/30"
                    >
                      <Save className="w-4 h-4 inline mr-1" />
                      Save
                    </button>
                    <button
                      onClick={() => setEditingDevice(null)}
                      className="px-3 py-1 bg-border/20 border border-border rounded text-text-tertiary hover:bg-border/30"
                    >
                      <X className="w-4 h-4 inline mr-1" />
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div>
                  <h3 className="text-lg font-semibold text-text-primary">{device.name}</h3>
                  <p className="text-sm text-primary uppercase">{device.type}</p>
                  <p className="text-xs text-text-tertiary">IP: {device.ip}</p>
                  <p className="text-xs text-text-tertiary">MAC: {device.mac}</p>
                  <p className="text-xs text-text-tertiary">User: {device.user || 'None'}</p>
                  <p className="text-xs text-text-tertiary">State: {device.state}</p>
                </div>
              )}
            </motion.div>
          ))}
        </div>
        {showAddDevice && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="mt-4 glass rounded-2xl p-6 border border-primary/30 bg-card/20"
          >
            <h3 className="text-lg font-semibold text-primary mb-4">Add New Device</h3>
            <div className="space-y-3">
              <input
                value={newDevice.name}
                onChange={(e) => setNewDevice({ ...newDevice, name: e.target.value })}
                className="w-full p-2 bg-card rounded text-text-primary"
                placeholder="Name"
              />
              <select
                value={newDevice.type}
                onChange={(e) => setNewDevice({ ...newDevice, type: e.target.value })}
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
                onChange={(e) => setNewDevice({ ...newDevice, ip: e.target.value })}
                className="w-full p-2 bg-card rounded text-text-primary"
                placeholder="IP"
              />
              <input
                value={newDevice.mac}
                onChange={(e) => setNewDevice({ ...newDevice, mac: e.target.value })}
                className="w-full p-2 bg-card rounded text-text-primary"
                placeholder="MAC"
              />
              <select
                value={newDevice.user}
                onChange={(e) => setNewDevice({ ...newDevice, user: e.target.value })}
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
          </motion.div>
        )}

        {/* Modals */}
        <UserModal
          isOpen={showUserModal}
          onClose={closeUserModal}
          user={modalUser}
          devices={userDevices}
          onDeviceClick={handleDeviceHistoryClick}
        />

        <DeviceHistoryModal
          isOpen={showDeviceModal}
          onClose={closeDeviceModal}
          device={modalDevice}
          history={deviceHistory}
        />
      </div>
    </div>
  );
};

export default PersonnelRoster;