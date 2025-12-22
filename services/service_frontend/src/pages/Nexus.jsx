import { motion } from 'framer-motion';
import { useState } from 'react';
import Core from '../components/Core';
import SituationalAwareness from '../components/SituationalAwareness';
import OnlineUsers from '../components/OnlineUsers';
import GuestRoster from '../components/GuestRoster';
import ContainerHealth from '../components/ContainerHealth';
import EventStream from '../components/EventStream';
 import TacticalPanelVariant1 from '../components/TacticalPanelVariant1';
 import TacticalPanelVariant2 from '../components/TacticalPanelVariant2';
 import TacticalPanelVariant3 from '../components/TacticalPanelVariant3';
 import LocationPanel from '../components/LocationPanel';
import TimeDatePanel from '../components/TimeDatePanel';
import WeatherPanel from '../components/WeatherPanel';
import CalendarPanel from '../components/CalendarPanel';
import CollapsibleSidePanel from '../components/CollapsibleSidePanel';

const Nexus = () => {
  const [systemHealth] = useState('cyan');
  const [locationTitle, setLocationTitle] = useState('');
  const [openPanels, setOpenPanels] = useState({
    timeDate: false,
    weather: false,
    calendar: false,
    containerHealth: false
  });

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.8 }}
      className="min-h-screen p-8 bg-fui-bg relative"
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

            <div className="flex justify-center">
                <div className="grid gap-8 grid-cols-1 md:grid-cols-[300px_450px_300px]">
              {/* Column 2: Residents Roster + Event Stream */}
               <motion.div
                 initial={{ opacity: 0, y: -20 }}
                 animate={{ opacity: 1, y: 0 }}
                 transition={{ delay: 0.5, duration: 0.6 }}
                 className="flex flex-col gap-4 order-3 md:order-none"
               >
                 <TacticalPanelVariant3 title="R3sidents">
                   <OnlineUsers />
                 </TacticalPanelVariant3>
                 <TacticalPanelVariant2 title="3vent:5tream">
                   <EventStream />
                 </TacticalPanelVariant2>
              </motion.div>

           {/* Column 3: Core + Situational Awareness */}
             <motion.div
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.6, duration: 0.8 }}
                className="flex flex-col gap-8 px-6 items-center order-1 md:order-none"
              >
              <Core health={systemHealth} />
               <TacticalPanelVariant1 title="Situat1onal Awar3ness">
                 <SituationalAwareness />
               </TacticalPanelVariant1>
            </motion.div>

            {/* Column 4: Guest Roster + Location Panel */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.7, duration: 0.6 }}
                className="flex flex-col gap-6 order-2 md:order-none"
              >
                <TacticalPanelVariant1 title="Gue5t R0ster">
                  <GuestRoster />
                </TacticalPanelVariant1>
                 <TacticalPanelVariant3 title={locationTitle}>
                   <LocationPanel setTitle={setLocationTitle} />
                 </TacticalPanelVariant3>
             </motion.div>

                </div>
            </div>

         {/* Collapsible Side Panels */}
          <CollapsibleSidePanel
            position="left"
            title="TIME & DAT3"
            isOpen={openPanels.timeDate}
            onToggle={() => setOpenPanels(prev => ({ ...prev, timeDate: !prev.timeDate }))}
            onClose={() => setOpenPanels(prev => ({ ...prev, timeDate: false }))}
            tabIndex={0}
          >
           <TacticalPanelVariant1 title="TIME & DATE">
             <TimeDatePanel />
           </TacticalPanelVariant1>
         </CollapsibleSidePanel>

          <CollapsibleSidePanel
            position="left"
            title="W3ATH3R"
            isOpen={openPanels.weather}
            onToggle={() => setOpenPanels(prev => ({ ...prev, weather: !prev.weather }))}
            onClose={() => setOpenPanels(prev => ({ ...prev, weather: false }))}
            tabIndex={1}
          >
           <TacticalPanelVariant2 title="WEATHER">
             <WeatherPanel />
           </TacticalPanelVariant2>
         </CollapsibleSidePanel>

          <CollapsibleSidePanel
            position="left"
            title="C4L3ND4R"
            isOpen={openPanels.calendar}
            onToggle={() => setOpenPanels(prev => ({ ...prev, calendar: !prev.calendar }))}
            onClose={() => setOpenPanels(prev => ({ ...prev, calendar: false }))}
            tabIndex={2}
          >
           <TacticalPanelVariant3 title="C4lendar">
             <CalendarPanel />
           </TacticalPanelVariant3>
         </CollapsibleSidePanel>

          <CollapsibleSidePanel
            position="right"
            title="C0NT41N3R H3ALTH"
            isOpen={openPanels.containerHealth}
            onToggle={() => setOpenPanels(prev => ({ ...prev, containerHealth: !prev.containerHealth }))}
            onClose={() => setOpenPanels(prev => ({ ...prev, containerHealth: false }))}
            tabIndex={0}
          >
           <TacticalPanelVariant2 title="Container Health">
             <ContainerHealth />
           </TacticalPanelVariant2>
         </CollapsibleSidePanel>
      </div>
    </motion.div>
  );
};

export default Nexus;
