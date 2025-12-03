import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import { Mail, Calendar } from 'lucide-react';
import Routines from '../components/Routines';
import Personality from '../components/Personality';
import Integrations from '../components/Integrations';
import System from '../components/System';
import TacticalPanel from '../components/TacticalPanel';
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
      className="min-h-screen p-8 bg-fui-bg"
      style={{
        backgroundImage: "linear-gradient(to right, #222 1px, transparent 1px), linear-gradient(to bottom, #222 1px, transparent 1px)",
        backgroundSize: '20px 20px'
      }}
    >
      <div className="max-w-7xl mx-auto">
        <motion.h1
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2, duration: 0.5 }}
          className="text-4xl font-tech font-bold text-fui-accent mb-4 text-center uppercase tracking-widest"
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
          <div className="flex items-center space-x-2 bg-fui-panel border border-fui-border rounded-none px-4 py-2">
            <Mail className="w-5 h-5 text-fui-accent" />
            <span className="text-sm font-mono text-fui-text">[ GMAIL ]</span>
            {integrationStatus.gmail ? (
              <span className="text-fui-accent font-mono text-xs">[ ONLINE ]</span>
            ) : (
              <span className="text-error font-mono text-xs">[ OFFLINE ]</span>
            )}
          </div>
          <div className="flex items-center space-x-2 bg-fui-panel border border-fui-border rounded-none px-4 py-2">
            <Calendar className="w-5 h-5 text-fui-accent" />
            <span className="text-sm font-mono text-fui-text">[ CALENDAR ]</span>
            {integrationStatus.calendar ? (
              <span className="text-fui-accent font-mono text-xs">[ ONLINE ]</span>
            ) : (
              <span className="text-error font-mono text-xs">[ OFFLINE ]</span>
            )}
          </div>
        </motion.div>

        <div className="flex">
          {/* Vertical Tabs */}
          <div className="w-64 mr-8">
            <TacticalPanel title="Systems" className="p-0">
              <div className="p-4">
                {tabs.map((tab, index) => (
                  <motion.button
                    key={tab.id}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.1, duration: 0.3 }}
                    onClick={() => setActiveTab(tab.id)}
                    className={`w-full text-left py-3 px-4 rounded-none mb-2 transition-all duration-300 font-mono text-sm border-l-2 ${
                      activeTab === tab.id
                        ? 'bg-fui-accent text-fui-bg border-fui-accent font-bold'
                        : 'text-fui-text border-fui-border hover:text-fui-accent hover:bg-fui-dim'
                    }`}
                  >
                    [ {tab.label.toUpperCase()} ]
                  </motion.button>
                ))}
              </div>
            </TacticalPanel>
          </div>

          {/* Content */}
          <div className="flex-1">
            <TacticalPanel title={tabs.find(tab => tab.id === activeTab)?.label || 'System'} className="min-h-[600px]">
              <motion.div
                key={activeTab}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3 }}
              >
                {ActiveComponent && <ActiveComponent />}
              </motion.div>
            </TacticalPanel>
          </div>
        </div>
      </div>
    </motion.div>
  );
};

export default Matrix;
