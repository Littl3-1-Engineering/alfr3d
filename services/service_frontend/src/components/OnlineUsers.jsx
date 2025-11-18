import { motion } from 'framer-motion';
import { User } from 'lucide-react';
import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';

const OnlineUsers = () => {
  const [users, setUsers] = useState([]);

  useEffect(() => {
    const fetchUsers = async () => {
      try {
        const response = await fetch(API_BASE_URL + '/api/users?online=true');
        const data = await response.json();
        console.log('Fetched users:', data);
        setUsers(data);
      } catch (error) {
        console.error('Error fetching users:', error);
      }
    };
    fetchUsers();
    // Fetch every 5 seconds
    const interval = setInterval(fetchUsers, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="glass rounded-2xl p-6 border border-primary/30 bg-card/20">
      <h2 className="text-xl font-bold text-primary mb-4 drop-shadow-lg">Online Users</h2>

        <div className="space-y-3">
          {users.map((user, index) => (
            <motion.div
              key={user.name}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.1, duration: 0.3 }}
              className="flex items-center space-x-2 py-1"
            >
              <User className={`w-4 h-4 ${user.type !== 'guest' ? 'text-success' : 'text-warning'}`} />
              <span className="text-sm text-text-secondary">{user.name}</span>
            </motion.div>
          ))}
        </div>
    </div>
  );
};

export default OnlineUsers;