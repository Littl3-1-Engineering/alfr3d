import { motion } from 'framer-motion';
import { useState, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import Lottie from 'lottie-react';
import { API_BASE_URL } from '../config';
import Core from '../components/Core';
import SituationalAwareness from '../components/SituationalAwareness';
import OnlineUsers from '../components/OnlineUsers';
import GuestRoster from '../components/GuestRoster';
import ContainerHealth from '../components/ContainerHealth';
import EventStream from '../components/EventStream';
import ResidentsSummary from '../components/ResidentsSummary';
 import TacticalPanelVariant1 from '../components/TacticalPanelVariant1';
 import TacticalPanelVariant2 from '../components/TacticalPanelVariant2';
 import TacticalPanelVariant3 from '../components/TacticalPanelVariant3';
 import LocationPanel from '../components/LocationPanel';
import TimeDatePanel from '../components/TimeDatePanel';
import WeatherPanel from '../components/WeatherPanel';
import CalendarPanel from '../components/CalendarPanel';
import CollapsibleSidePanel from '../components/CollapsibleSidePanel';
import ProjectTreeViz from '../components/ProjectTreeViz';
import ErrorBoundary from '../components/ErrorBoundary';
import CameraStream from '../components/CameraStream';
import { useTheme } from '../utils/useTheme';

const BOOT_MESSAGES = [
  { msg: '[ OK ] Loading kernel modules...', delay: 200 },
  { msg: '[ OK ] Initializing network stack...', delay: 400 },
  { msg: '[WARN] ALFR3D firewall rules: 3 active, 2 legacy', delay: 600 },
  { msg: '[ OK ] Mounting filesystems...', delay: 900 },
  { msg: '[INFO] Scan root: /project (max depth: 3)', delay: 1100 },
  { msg: '[ OK ] Starting container orchestration...', delay: 1400 },
  { msg: '[ OK ] Establishing websocket gateway...', delay: 1700 },
  { msg: '[INFO] Device registry: 12 registered, 8 online', delay: 2000 },
  { msg: '[ OK ] Initializing sensor fusion pipeline...', delay: 2300 },
  { msg: '[INFO] Core temperature: nominal', delay: 2600 },
  { msg: '[ OK ] Nexus subsystems: all green', delay: 2900 },
  { msg: '[ OK ] ALFR3D Nexus ready.', delay: 3200 },
];

const NexusLoader = () => {
  const [animationData, setAnimationData] = useState(null);
  const [logIndex, setLogIndex] = useState(0);
  const [glitch, setGlitch] = useState(false);
  const logEndRef = useRef(null);
  const { themeColors } = useTheme();

  useEffect(() => {
    fetch('/assets/lottie/logo.json')
      .then(r => r.json())
      .then(setAnimationData)
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (logIndex < BOOT_MESSAGES.length) {
      const timer = setTimeout(() => setLogIndex(i => i + 1), BOOT_MESSAGES[logIndex].delay);
      return () => clearTimeout(timer);
    }
  }, [logIndex]);

  useEffect(() => {
    const glitchInterval = setInterval(() => {
      setGlitch(true);
      setTimeout(() => setGlitch(false), 150);
    }, 4000 + Math.random() * 3000);
    return () => clearInterval(glitchInterval);
  }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logIndex]);

  return (
    <div className="min-h-screen p-8 bg-fui-bg flex flex-col items-center justify-center relative overflow-hidden">
      <div className="boot-scanline" />
      <div
        className={`relative z-10 flex flex-col items-center ${glitch ? 'boot-glitch' : ''}`}
        style={glitch ? { animation: 'boot-glitch 0.15s ease-in-out' } : undefined}
      >
        <div className="w-40 h-40 mb-4">
          {animationData && (
            <Lottie animationData={animationData} loop autoplay />
          )}
        </div>
        <div className="w-[420px] max-w-full">
          <div className="bg-card/70 border border-fui-accent/30 rounded p-4 font-mono text-xs min-h-[260px] max-h-[320px] overflow-y-auto">
            {BOOT_MESSAGES.slice(0, logIndex + 1).map((m, i) => {
              const isWarn = m.msg.startsWith('[WARN]');
              const isInfo = m.msg.startsWith('[INFO]');
              const isReady = m.msg.includes('ready.');
              const lineColor = isReady
                ? themeColors.primary
                : isWarn
                  ? themeColors.warning
                  : isInfo
                    ? themeColors.textSecondary
                    : themeColors.textPrimary;
              const promptColor = isWarn
                ? themeColors.warning
                : isInfo
                  ? themeColors.textSecondary
                  : themeColors.primary;
              return (
                <p
                  key={i}
                  className="boot-log-line whitespace-nowrap"
                  style={{
                    color: lineColor,
                    animationDelay: '0s',
                  }}
                >
                  <span style={{ color: promptColor }}>{'>'}</span>{' '}
                  {m.msg}
                </p>
              );
            })}
            {logIndex <= BOOT_MESSAGES.length - 1 && (
              <span className="inline-block w-2 h-4 bg-fui-accent ml-1 align-middle" style={{ animation: 'boot-cursor-blink 1s step-end infinite' }} />
            )}
            <div ref={logEndRef} />
          </div>
          <p className="text-center text-[10px] text-fui-accent/50 font-mono mt-2 tracking-widest uppercase">
            Initializing nexus...
          </p>
        </div>
      </div>
    </div>
  );
};

const Nexus = () => {
  const [systemHealth] = useState('cyan');
  const [locationTitle, setLocationTitle] = useState('');
  const [openPanels, setOpenPanels] = useState({
    timeDate: false,
    weather: false,
    calendar: false,
    containerHealth: false,
    projectTree: false,
    camera: false
  });

  const fetchJson = (url) => fetch(url).then(r => r.ok ? r.json() : Promise.reject(r.status));

  const { data: weather, error: weatherError } = useQuery({ queryKey: ['weather'], queryFn: () => fetchJson(`${API_BASE_URL}/api/weather`), staleTime: 5 * 60 * 1000 });
  const { data: containers, error: containersError } = useQuery({ queryKey: ['containers'], queryFn: () => fetchJson(`${API_BASE_URL}/api/containers`), staleTime: 5 * 60 * 1000 });
  const { data: devices, error: devicesError } = useQuery({ queryKey: ['devices'], queryFn: () => fetchJson(`${API_BASE_URL}/api/devices`), staleTime: 5 * 60 * 1000 });
  const { data: onlineUsers, error: usersError } = useQuery({ queryKey: ['online-users'], queryFn: () => fetchJson(`${API_BASE_URL}/api/users?online=true`), staleTime: 5 * 60 * 1000 });
  const { data: location, error: locationError } = useQuery({ queryKey: ['location'], queryFn: () => fetchJson(`${API_BASE_URL}/api/environment`), staleTime: 5 * 60 * 1000 });

  const hasData = weather !== undefined && containers !== undefined && devices !== undefined && onlineUsers !== undefined && location !== undefined;
  const anyError = weatherError || containersError || devicesError || usersError || locationError;
  const allFailed = weatherError && containersError && devicesError && usersError && locationError;
  const isLoading = !hasData && !anyError;

  const filterGuests = (users) => {
    if (!users) return [];
    return users.filter(user => user.type === 'guest');
  };

  const filterResidents = (users) => {
    if (!users) return [];
    return users.filter(user => user.state === 'online' && ['technoking', 'owner', 'resident'].includes(user.type));
  };

  if (allFailed) {
    return (
      <div className="min-h-screen p-8 bg-fui-bg flex flex-col items-center justify-center">
        <p className="text-fui-accent font-mono uppercase text-xl mb-4">NEXUS OFFLINE</p>
        <p className="text-fui-text font-mono text-sm mb-2">Unable to connect to backend services</p>
        <button
          onClick={() => window.location.reload()}
          className="mt-4 px-6 py-2 border border-fui-accent text-fui-accent font-mono uppercase text-sm hover:bg-fui-accent hover:text-black transition-colors"
        >
          RETRY
        </button>
      </div>
    );
  }

  if (isLoading) {
    return <NexusLoader />;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.8 }}
      className="min-h-screen p-8 bg-fui-bg relative"
      style={{
        backgroundImage: "linear-gradient(to right, var(--theme-tactical-grid) 1px, transparent 1px), linear-gradient(to bottom, var(--theme-tactical-grid) 1px, transparent 1px)",
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

            <div className="mb-6">
              <ResidentsSummary residents={filterResidents(onlineUsers).length} guests={filterGuests(onlineUsers).length} />
            </div>

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
                    <OnlineUsers initialResidents={onlineUsers} />
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
              <Core health={systemHealth} initialContainers={containers} initialDevices={devices} initialUsers={onlineUsers} />
<TacticalPanelVariant1 title="Situat1onal Awar3ness">
                  <SituationalAwareness timezone={location?.timezone} />
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
                   <GuestRoster initialGuests={filterGuests(onlineUsers)} />
                 </TacticalPanelVariant1>
                  <TacticalPanelVariant3 title={locationTitle}>
                    <LocationPanel setTitle={setLocationTitle} initialLocation={location} />
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
              <TimeDatePanel timezone={location?.timezone} />
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
              <WeatherPanel initialWeather={weather} />
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
              <ContainerHealth initialContainers={containers} />
            </TacticalPanelVariant2>
          </CollapsibleSidePanel>

          <CollapsibleSidePanel
            position="right"
            title="PR0J3CT TR33"
            isOpen={openPanels.projectTree}
            onToggle={() => setOpenPanels(prev => ({ ...prev, projectTree: !prev.projectTree }))}
            onClose={() => setOpenPanels(prev => ({ ...prev, projectTree: false }))}
            tabIndex={1}
          >
            <TacticalPanelVariant1 title="Pr0j3ct Tr33">
              <ErrorBoundary>
                <ProjectTreeViz />
              </ErrorBoundary>
            </TacticalPanelVariant1>
          </CollapsibleSidePanel>

          <CollapsibleSidePanel
            position="right"
            title="C4M3R4"
            isOpen={openPanels.camera}
            onToggle={() => setOpenPanels(prev => ({ ...prev, camera: !prev.camera }))}
            onClose={() => setOpenPanels(prev => ({ ...prev, camera: false }))}
            tabIndex={2}
          >
            <TacticalPanelVariant2 title="Cam3ra Str3am">
              <CameraStream />
            </TacticalPanelVariant2>
          </CollapsibleSidePanel>
      </div>
    </motion.div>
  );
};

export default Nexus;
