import { motion } from 'framer-motion';
import { useState } from 'react';
import Core from '../components/Core';
import SituationalAwareness from '../components/SituationalAwareness';
import OnlineUsers from '../components/OnlineUsers';
import GuestRoster from '../components/GuestRoster';
import ContainerHealth from '../components/ContainerHealth';
import EventStream from '../components/EventStream';
import TacticalPanel from '../components/TacticalPanel';
import LocationPanel from '../components/LocationPanel';
import TimeDatePanel from '../components/TimeDatePanel';
import WeatherPanel from '../components/WeatherPanel';
import CalendarPanel from '../components/CalendarPanel';

const Nexus = () => {
  const [systemHealth] = useState('cyan');

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
      <div className="w-full px-8">
        <motion.h1
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2, duration: 0.5 }}
          className="text-4xl font-tech font-bold text-fui-accent mb-8 text-center uppercase tracking-widest"
        >
          ALFR3D Nexus
        </motion.h1>

          <div className="grid gap-8 w-full grid-cols-1 md:grid-cols-5 md:grid-nexus">
           {/* Column 1: Time, Weather, Calendar */}
            <motion.div
              initial={{ opacity: 0, x: -50 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.4, duration: 0.6 }}
              className="flex flex-col gap-4 order-4 md:order-none"
            >
             <TimeDatePanel />
             <WeatherPanel />
             <CalendarPanel />
            </motion.div>
            {/* Column 2: Location + Situational Awareness */}
             <motion.div
               initial={{ opacity: 0, y: -20 }}
               animate={{ opacity: 1, y: 0 }}
               transition={{ delay: 0.5, duration: 0.6 }}
               className="flex flex-col gap-4 order-3 md:order-none"
             >
              <LocationPanel />
              <TacticalPanel title="Situational Awareness">
                <SituationalAwareness />
              </TacticalPanel>
            </motion.div>

          {/* Column 3: Core + Event Stream */}
           <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.6, duration: 0.8 }}
              className="flex flex-col gap-8 px-6 items-center order-1 md:order-none"
            >
            <Core health={systemHealth} />
            <TacticalPanel title="Event Stream">
              <EventStream />
            </TacticalPanel>
          </motion.div>

           {/* Column 4: Guest Roster + Residents */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.7, duration: 0.6 }}
              className="flex flex-col gap-6 order-2 md:order-none"
            >
             <TacticalPanel title="Guest Roster">
               <GuestRoster />
             </TacticalPanel>
             <TacticalPanel title="R3sidents">
               <OnlineUsers />
             </TacticalPanel>
           </motion.div>

           {/* Column 5: Container Health */}
            <motion.div
              initial={{ opacity: 0, x: 50 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.8, duration: 0.6 }}
              className="flex flex-col order-5 md:order-none"
            >
             <TacticalPanel title="Container Health">
               <ContainerHealth />
             </TacticalPanel>
           </motion.div>
        </div>
      </div>
    </motion.div>
  );
};

export default Nexus;
