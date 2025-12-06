import { motion } from 'framer-motion';
import { useState, useEffect, useRef } from 'react';
import { User } from 'lucide-react';
import { API_BASE_URL } from '../config';
import { getGravatarUrl } from '../utils/gravatarUtils';
import { formatCreatedDate } from '../utils/timeUtils';

const OnlineUsers = () => {
  const [residents, setResidents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(false);
  const hasLoadedInitially = useRef(false);

  useEffect(() => {
    const fetchResidents = async () => {
      try {
        setIsLoading(!hasLoadedInitially.current);
        setError(false);
        const response = await fetch(`${API_BASE_URL}/api/users?online=true`);
        if (response.ok) {
          const data = await response.json();
          const onlineResidents = data.filter(user => ['technoking', 'owner', 'resident'].includes(user.type));
          setResidents(onlineResidents);
          if (!hasLoadedInitially.current) {
            hasLoadedInitially.current = true;
          }
        } else {
          if (!hasLoadedInitially.current) {
            setError(true);
          }
        }
      } catch (error) {
        console.error('Failed to fetch online residents:', error);
        if (!hasLoadedInitially.current) {
          setError(true);
        }
      } finally {
        setIsLoading(false);
      }
    };

    fetchResidents();
    const residentTimer = setInterval(fetchResidents, 5000); // Update every 5 seconds
    return () => clearInterval(residentTimer);
  }, []);

  const formatDate = (dateString) => {
    if (!dateString) return 'UNKNOWN';
    return new Date(dateString).toLocaleDateString();
  };



  // Generate random barcode lines
  const generateBarcode = () => {
    return Array.from({ length: 15 }, (_, i) => ({
      height: Math.random() * 6 + 2, // 2-8px
      width: Math.random() * 2 + 1, // 1-3px
      opacity: Math.random() * 0.5 + 0.3, // 0.3-0.8
      key: i
    }));
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-fui-panel border border-fui-border rounded-none p-4 text-center"
        >
          <p className="text-fui-accent font-mono uppercase text-sm">LOADING RESIDENT DATA...</p>
        </motion.div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-fui-panel border border-fui-border rounded-none p-4 text-center"
        >
          <p className="text-red-400 font-mono uppercase text-sm">RESIDENT DATA UNAVAILABLE</p>
        </motion.div>
      </div>
    );
  }

  if (residents.length === 0) {
    return (
      <div className="space-y-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-fui-panel border border-fui-border rounded-none p-4 text-center"
        >
          <p className="text-fui-text font-mono uppercase text-sm">NO RESIDENTS FOUND</p>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {residents.map((resident, index) => (
        <motion.div
          key={resident.name || index}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: index * 0.1, duration: 0.5 }}
          className="relative bg-fui-panel border border-fui-border rounded-none overflow-hidden"
        >
          {/* Corner Markers */}
          <div className="absolute -top-px -left-px w-3 h-3 border-t-2 border-l-2 border-fui-accent z-10" />
          <div className="absolute -top-px -right-px w-3 h-3 border-t-2 border-r-2 border-fui-accent z-10" />
          <div className="absolute -bottom-px -left-px w-3 h-3 border-b-2 border-l-2 border-fui-accent z-10" />
          <div className="absolute -bottom-px -right-px w-3 h-3 border-b-2 border-r-2 border-fui-accent z-10" />

          {/* Folder Tab */}
          <div className="absolute top-0 left-0 border-r-4 border-fui-accent bg-black/60 px-2 py-1 z-20">
            <h4 className="font-tech text-sm text-white uppercase">RESIDENT</h4>
          </div>

          {/* Main Content */}
          <div className="flex items-center gap-4 p-4 pt-8">
            {/* Avatar */}
            <div className="flex-shrink-0 w-16 h-16 bg-gray-700 rounded flex items-center justify-center">
              {getGravatarUrl(resident.email) ? (
                <img
                  src={getGravatarUrl(resident.email)}
                  alt={`${resident.name} avatar`}
                  className="w-full h-full rounded object-cover"
                />
              ) : (
                <User size={32} className="text-gray-400 filter grayscale opacity-60" />
              )}
            </div>

             {/* Info */}
             <div className="flex-1 min-w-0 overflow-hidden">
               <h3 className="font-tech text-xl uppercase text-white mb-1">{resident.name}</h3>
                <p className="font-mono text-sm text-fui-text" style={{ maskImage: 'linear-gradient(to right, black 80%, transparent 100%)', WebkitMaskImage: 'linear-gradient(to right, black 80%, transparent 100%)' }}>{resident.email}</p>
             </div>

            {/* Barcode */}
            <div className="flex-shrink-0 w-10 h-20 bg-black/20 flex flex-col items-center justify-center relative">
              <div className="flex flex-col space-y-0.5">
                {generateBarcode().map((line) => (
                  <div
                    key={line.key}
                    className="bg-fui-accent"
                    style={{
                      height: `${line.height}px`,
                      width: `${line.width}px`,
                      opacity: line.opacity
                    }}
                  />
                ))}
              </div>
                <div className="absolute bottom-1 left-1/2 transform -translate-x-1/2 origin-center rotate-[-90deg]">
                  <span className="font-mono text-xs text-fui-text">{formatCreatedDate(resident.created_at)}</span>
                </div>
            </div>
          </div>

           {/* Footer */}
            <div className="bg-fui-accent text-black font-mono text-xs px-4 py-2 text-center">
              LAST ONLINE: {formatDate(resident.last_online)}
            </div>
        </motion.div>
      ))}
    </div>
  );
};

export default OnlineUsers;
