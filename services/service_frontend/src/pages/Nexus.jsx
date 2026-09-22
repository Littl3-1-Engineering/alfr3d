import { motion } from 'framer-motion';
import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Lottie } from 'lottie-react';
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
import FavoritesPanel from '../components/FavoritesPanel';
import ProjectTreeViz from '../components/ProjectTreeViz';
import ErrorBoundary from '../components/ErrorBoundary';
import CameraStream from '../components/CameraStream';
import NowPlayingCard from '../components/NowPlayingCard';
import HudRing from '../components/HudRing';
import { useTheme } from '../utils/useTheme';
import { useUiPrefs } from '../utils/useUiPrefs';

// `shape` turns the boot log into a HUD checklist instead of scrolling text: each line's
// ring spins while that line is the current step and bounce-settles as it completes. The
// shape says what kind of work the step is (see the vocabulary in
// todo/todo_cyber_hud_buttons_frontend.md) — gear for local work, splitArc for anything
// talking to something else, compass for a reading that got acquired, sensor for a plain
// readout, scanner for the line that wants attention.
const BOOT_MESSAGES = [
  { msg: '[ OK ] Loading kernel modules...', delay: 200, shape: 'gear' },
  { msg: '[ OK ] Initializing network stack...', delay: 400, shape: 'splitArc' },
  { msg: '[WARN] ALFR3D firewall rules: 3 active, 2 legacy', delay: 600, shape: 'scanner' },
  { msg: '[ OK ] Mounting filesystems...', delay: 900, shape: 'gear' },
  { msg: '[INFO] Scan root: /project (max depth: 3)', delay: 1100, shape: 'sensor' },
  { msg: '[ OK ] Starting container orchestration...', delay: 1400, shape: 'gear' },
  { msg: '[ OK ] Establishing websocket gateway...', delay: 1700, shape: 'splitArc' },
  { msg: '[INFO] Device registry: 12 registered, 8 online', delay: 2000, shape: 'compass' },
  { msg: '[ OK ] Initializing sensor fusion pipeline...', delay: 2300, shape: 'gear' },
  { msg: '[INFO] Core temperature: nominal', delay: 2600, shape: 'sensor' },
  { msg: '[ OK ] Nexus subsystems: all green', delay: 2900, shape: 'compass' },
  { msg: '[ OK ] ALFR3D Nexus ready.', delay: 3200, shape: 'compass' },
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
            <Lottie src={animationData} loop autoplay />
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
              // Exactly one ring is ever in motion: the step being worked on. Everything
              // above it has already bounce-settled, and the warning line sits frozen.
              const ringState = isWarn
                ? 'fault'
                : i < logIndex
                  ? 'resolve'
                  : 'working';
              return (
                <p
                  key={i}
                  className="boot-log-line whitespace-nowrap flex items-center gap-2"
                  style={{
                    color: lineColor,
                    animationDelay: '0s',
                  }}
                >
                  <HudRing shape={m.shape} state={ringState} size={14} />
                  <span>{m.msg}</span>
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
  const { nexusNav } = useUiPrefs();
  const tabsMode = nexusNav === 'tabs';
  const [systemHealth] = useState('cyan');
  const [locationTitle, setLocationTitle] = useState('');
  const [favoritesOpen, setFavoritesOpen] = useState(false);
  const [openPanels, setOpenPanels] = useState({
    timeDate: false,
    weather: false,
    calendar: false,
    containerHealth: false,
    projectTree: false,
    camera: false
  });

  const togglePanel = useCallback((id) => {
    setOpenPanels(prev => ({ ...prev, [id]: !prev[id] }));
  }, []);

  // The ring of launchers around the Core. Every panel reachable from Nexus is here, and
  // each gets its own shape so the ring is learnable by silhouette rather than by reading
  // labels. Empty in tabs mode: the edge tabs are then the only control, and an empty ring
  // is what hides it -- Core renders exactly what it is handed.
  //
  // Where a shape can mean something it does: Container Health takes the Gear Dial that its
  // own container satellites wear, Quick Controls takes the Split-Arc because it reaches out
  // to devices, Camera takes the Iris. The Compass stays reserved for presence.
  const launchers = useMemo(() => tabsMode ? [] : [
    { id: 'favorites', label: 'Quick Controls', shape: 'splitArc', isOpen: favoritesOpen, onToggle: () => setFavoritesOpen(v => !v) },
    { id: 'timeDate', label: 'Time & Date', shape: 'sensor', isOpen: openPanels.timeDate, onToggle: () => togglePanel('timeDate') },
    { id: 'weather', label: 'Weather', shape: 'scanner', isOpen: openPanels.weather, onToggle: () => togglePanel('weather') },
    { id: 'calendar', label: 'Calendar', shape: 'reticle', isOpen: openPanels.calendar, onToggle: () => togglePanel('calendar') },
    { id: 'containerHealth', label: 'Container Health', shape: 'gear', isOpen: openPanels.containerHealth, onToggle: () => togglePanel('containerHealth') },
    { id: 'projectTree', label: 'Project Tree', shape: 'node', isOpen: openPanels.projectTree, onToggle: () => togglePanel('projectTree') },
    { id: 'camera', label: 'Camera', shape: 'iris', isOpen: openPanels.camera, onToggle: () => togglePanel('camera') },
  ], [tabsMode, favoritesOpen, openPanels, togglePanel]);

  // In tabs mode the edge tab is the control, so it owns the toggle; in ring mode the
  // panels are opened from the Core and only ever close themselves.
  const tabProps = useCallback((id) => (
    tabsMode ? { showTab: true, onToggle: () => togglePanel(id) } : {}
  ), [tabsMode, togglePanel]);

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
                 className="flex flex-col gap-4 order-3 md:order-none min-w-0"
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
                className="flex flex-col gap-8 px-6 items-center order-1 md:order-none min-w-0"
              >
              <Core
                health={systemHealth}
                initialContainers={containers}
                initialDevices={devices}
                initialUsers={onlineUsers}
                onClick={() => setFavoritesOpen(v => !v)}
                launchers={launchers}
              />
<TacticalPanelVariant1 title="Situat1onal Awar3ness" className="w-full">
                  <SituationalAwareness timezone={location?.timezone} />
                </TacticalPanelVariant1>
            </motion.div>

            {/* Column 4: Guest Roster + Location Panel */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.7, duration: 0.6 }}
                className="flex flex-col gap-6 order-2 md:order-none min-w-0"
              >
<TacticalPanelVariant1 title="Gue5t R0ster">
                   <GuestRoster initialGuests={filterGuests(onlineUsers)} />
                 </TacticalPanelVariant1>
<ErrorBoundary>
                  <NowPlayingCard />
                </ErrorBoundary>
                  <TacticalPanelVariant3 title={locationTitle}>
                    <LocationPanel setTitle={setLocationTitle} initialLocation={location} />
                  </TacticalPanelVariant3>
             </motion.div>

                </div>
            </div>

         <FavoritesPanel isOpen={favoritesOpen} onClose={() => setFavoritesOpen(false)} />

         {/* Collapsible Side Panels */}
          <CollapsibleSidePanel
            position="left"
            title="TIME & DAT3"
            isOpen={openPanels.timeDate}
            onClose={() => setOpenPanels(prev => ({ ...prev, timeDate: false }))}
            {...tabProps('timeDate')}
            slot={0}
          >
<TacticalPanelVariant1 title="TIME & DATE">
              <TimeDatePanel timezone={location?.timezone} />
            </TacticalPanelVariant1>
         </CollapsibleSidePanel>

          <CollapsibleSidePanel
            position="left"
            title="W3ATH3R"
            isOpen={openPanels.weather}
            onClose={() => setOpenPanels(prev => ({ ...prev, weather: false }))}
            {...tabProps('weather')}
            slot={1}
          >
<TacticalPanelVariant2 title="WEATHER">
              <WeatherPanel initialWeather={weather} />
            </TacticalPanelVariant2>
         </CollapsibleSidePanel>

          <CollapsibleSidePanel
            position="left"
            title="C4L3ND4R"
            isOpen={openPanels.calendar}
            onClose={() => setOpenPanels(prev => ({ ...prev, calendar: false }))}
            {...tabProps('calendar')}
            slot={2}
          >
<TacticalPanelVariant3 title="C4lendar">
              <CalendarPanel />
            </TacticalPanelVariant3>
         </CollapsibleSidePanel>

<CollapsibleSidePanel
            position="right"
            title="C0NT41N3R H3ALTH"
            isOpen={openPanels.containerHealth}
            onClose={() => setOpenPanels(prev => ({ ...prev, containerHealth: false }))}
            {...tabProps('containerHealth')}
            slot={0}
          >
            <TacticalPanelVariant2 title="Container Health">
              <ContainerHealth initialContainers={containers} />
            </TacticalPanelVariant2>
          </CollapsibleSidePanel>

          <CollapsibleSidePanel
            position="right"
            title="PR0J3CT TR33"
            isOpen={openPanels.projectTree}
            onClose={() => setOpenPanels(prev => ({ ...prev, projectTree: false }))}
            {...tabProps('projectTree')}
            slot={1}
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
            onClose={() => setOpenPanels(prev => ({ ...prev, camera: false }))}
            {...tabProps('camera')}
            slot={2}
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
