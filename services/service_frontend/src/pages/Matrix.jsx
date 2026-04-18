import { motion } from 'framer-motion';
import { useState, lazy, Suspense } from 'react';
import { Loader2 } from 'lucide-react';
import TacticalPanel from '../components/TacticalPanel';
import TacticalPanelVariant1 from '../components/TacticalPanelVariant1';
import TacticalPanelVariant2 from '../components/TacticalPanelVariant2';
import TacticalPanelVariant3 from '../components/TacticalPanelVariant3';
import TacticalPanelVariant4 from '../components/TacticalPanelVariant4';
import TacticalPanelVariant5 from '../components/TacticalPanelVariant5';
import TacticalPanelVariant6 from '../components/TacticalPanelVariant6';
import TacticalPanelVariant7 from '../components/TacticalPanelVariant7';

const Routines = lazy(() => import('../components/Routines'));
const Personality = lazy(() => import('../components/Personality'));
const Integrations = lazy(() => import('../components/Integrations'));
const System = lazy(() => import('../components/System'));

const LoadingFallback = () => (
  <div className="flex items-center justify-center h-64">
    <Loader2 className="w-8 h-8 text-fui-accent animate-spin" />
    <span className="ml-3 text-text-tertiary">Loading...</span>
  </div>
);

const Matrix = () => {
  const [activeTab, setActiveTab] = useState('routines');

  const tabs = [
    { id: 'routines', label: 'Routines', component: Routines },
    { id: 'personality', label: 'Personality', component: Personality },
    { id: 'integrations', label: 'Integrations', component: Integrations },
    { id: 'customizations', label: 'Customizations', component: null },
    { id: 'system', label: 'System', component: System },
  ];

  const ActiveComponent = tabs.find(tab => tab.id === activeTab)?.component;

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

        <div className="flex">
          {/* Vertical Tabs */}
          <div className="w-64 mr-8">
            <TacticalPanelVariant3 title="Systems" className="p-0">
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
            </TacticalPanelVariant3>
          </div>

          {/* Content */}
          <div className="flex-1">
            <TacticalPanelVariant1 title={tabs.find(tab => tab.id === activeTab)?.label || 'System'} className="min-h-[600px]">
              <motion.div
                key={activeTab}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3 }}
              >
                <Suspense fallback={<LoadingFallback />}>
                  {activeTab === 'customizations' ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <TacticalPanelVariant1 title="Panel Variant 1">
                        <div className="text-fui-text">
                          <p className="mb-2">Font: Tech / Rajdhani</p>
                          <p className="mb-2">Colors: Cyan accent (#06b6d4)</p>
                          <p className="mb-2">Style: L-shaped corner markers</p>
                          <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.</p>
                        </div>
                      </TacticalPanelVariant1>
                      <TacticalPanelVariant2 title="Panel Variant 2">
                        <div className="text-fui-text">
                          <p className="mb-2">Font: Tech / Rajdhani</p>
                          <p className="mb-2">Colors: Amber accent (#f59e0b)</p>
                          <p className="mb-2">Style: Striped header pattern</p>
                          <p>Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.</p>
                        </div>
                      </TacticalPanelVariant2>
                      <TacticalPanelVariant3 title="Panel Variant 3">
                        <div className="text-fui-text">
                          <p className="mb-2">Font: Tech / Rajdhani</p>
                          <p className="mb-2">Colors: Yellow accent (#eab308)</p>
                          <p className="mb-2">Style: Layered corners, gradient header</p>
                          <p>Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.</p>
                        </div>
                      </TacticalPanelVariant3>
                      <TacticalPanelVariant4 title="Panel Variant 4">
                        <div className="text-fui-text">
                          <p className="mb-2">Font: Mono / JetBrains</p>
                          <p className="mb-2">Colors: Amber terminal (#f59e0b)</p>
                          <p className="mb-2">Style: Scanlines, blinking cursor, ASCII corners</p>
                          <p>Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium.</p>
                        </div>
                      </TacticalPanelVariant4>
                      <TacticalPanelVariant5 title="Panel Variant 5">
                        <div className="text-fui-text">
                          <p className="mb-2">Font: Tech / Rajdhani</p>
                          <p className="mb-2">Colors: Amber (#f59e0b) + gray</p>
                          <p className="mb-2">Style: Industrial riveted frame, segmented lights</p>
                          <p>Totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae.</p>
                        </div>
                      </TacticalPanelVariant5>
                      <TacticalPanelVariant6 title="Panel Variant 6">
                        <div className="text-fui-text">
                          <p className="mb-2">Font: Tech / Rajdhani</p>
                          <p className="mb-2">Colors: Silver minimalist (#c0c0c0)</p>
                          <p className="mb-2">Style: Thin corner lines, centered text</p>
                          <p>Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit.</p>
                        </div>
                      </TacticalPanelVariant6>
                      <TacticalPanelVariant7 title="Panel Variant 7">
                        <div className="text-fui-text">
                          <p className="mb-2">Font: Tech / Rajdhani</p>
                          <p className="mb-2">Colors: Amber (#f59e0b)</p>
                          <p className="mb-2">Style: Diagonal brackets, glitch lines</p>
                          <p>Neque porro quisquam est, qui dolorem ipsum quia dolor sit amet, consectetur.</p>
                        </div>
                      </TacticalPanelVariant7>
                      <TacticalPanel title="Base Panel">
                        <div className="text-fui-text">
                          <p className="mb-2">Font: Tech / Rajdhani</p>
                          <p className="mb-2">Colors: Cyan accent (#06b6d4)</p>
                          <p className="mb-2">Style: Standard corners</p>
                          <p>Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.</p>
                        </div>
                      </TacticalPanel>
                    </div>
                  ) : ActiveComponent && <ActiveComponent />}
                </Suspense>
              </motion.div>
            </TacticalPanelVariant1>
          </div>
        </div>
      </div>
    </motion.div>
  );
};

export default Matrix;
