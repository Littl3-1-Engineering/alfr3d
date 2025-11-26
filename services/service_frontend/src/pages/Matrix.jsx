import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import { CheckCircle, XCircle, Mail, Calendar } from 'lucide-react';
import Routines from '../components/Routines';
import Personality from '../components/Personality';
import Integrations from '../components/Integrations';
import System from '../components/System';
import { API_BASE_URL } from '../config';

const Matrix = () => {
  const [activeTab, setActiveTab] = useState('routines');
  const [integrationStatus, setIntegrationStatus] = useState({ gmail: false, calendar: false });

  const tabs = [
    { id: 'routines', label: 'Routines', component: Routines },
    { id: 'personality', label: 'Personality', component: Personality },
    { id: 'integrations', label: 'Integrations', component: Integrations },
    { id: 'system', label: 'System', component: System },
  ];

  const ActiveComponent = tabs.find(tab => tab.id === activeTab)?.component;

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/integrations/status`);
        if (response.ok) {
          const status = await response.json();
          setIntegrationStatus(status);
        }
      } catch (error) {
        console.error('Error fetching integration status:', error);
      }
    };
    fetchStatus();
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.8 }}
      className="min-h-screen p-8"
    >
      <div className="max-w-7xl mx-auto">
        <motion.h1
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2, duration: 0.5 }}
          className="text-4xl font-bold text-primary mb-4 text-center drop-shadow-lg"
        >
          ALFR3D Matrix
        </motion.h1>

        {/* Integration Status */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4, duration: 0.5 }}
          className="flex justify-center space-x-6 mb-8"
        >
          <div className="flex items-center space-x-2 glass rounded-lg px-4 py-2">
            <Mail className="w-5 h-5 text-primary" />
            <span className="text-sm font-medium text-text-primary">Gmail</span>
            {integrationStatus.gmail ? (
              <CheckCircle className="w-5 h-5 text-success" />
            ) : (
              <XCircle className="w-5 h-5 text-error" />
            )}
          </div>
          <div className="flex items-center space-x-2 glass rounded-lg px-4 py-2">
            <Calendar className="w-5 h-5 text-primary" />
            <span className="text-sm font-medium text-text-primary">Calendar</span>
            {integrationStatus.calendar ? (
              <CheckCircle className="w-5 h-5 text-success" />
            ) : (
              <XCircle className="w-5 h-5 text-error" />
            )}
          </div>
        </motion.div>
        
        <div className="flex">
          {/* Vertical Tabs */}
          <div className="w-64 mr-8">
            <div className="glass rounded-2xl p-4">
              {tabs.map((tab, index) => (
                <motion.button
                  key={tab.id}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.1, duration: 0.3 }}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full text-left py-3 px-4 rounded-lg mb-2 transition-all duration-300 ${
                    activeTab === tab.id
                      ? 'bg-primary/20 text-primary border-l-4 border-primary drop-shadow-lg'
                      : 'text-text-tertiary hover:text-primary hover:bg-card/30'
                  }`}
                >
                  {tab.label}
                </motion.button>
              ))}
            </div>
          </div>
          
          {/* Content */}
          <div className="flex-1">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3 }}
              className="glass rounded-2xl p-6 min-h-[600px]"
            >
              {ActiveComponent && <ActiveComponent />}
            </motion.div>
          </div>
        </div>
      </div>
    </motion.div>
  );
};

export default Matrix;