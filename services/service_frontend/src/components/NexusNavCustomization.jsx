import { motion } from 'framer-motion';
import { Check, LayoutTemplate } from 'lucide-react';
import HudRing from './HudRing';
import { useUiPrefs } from '../utils/useUiPrefs';
import { NEXUS_NAV_MODES } from '../utils/nexusNav';

// Which control opens the Nexus side panels. `NEXUS_NAV_MODES` says which modes exist and
// in what order; this only supplies the copy and the preview for each.
const NAV_DETAILS = {
  rings: {
    label: 'Orbit Rings',
    description:
      'Animated HUD rings orbit the Core, one per panel. Each shape is distinct, so the ring is learnable by silhouette, and an open panel keeps its node lit.',
  },
  tabs: {
    label: 'Edge Tabs',
    description:
      'Vertical-text tabs pinned to the left and right edges of the screen, labelled in full. The Core still opens Quick Controls on click.',
  },
};

// The four shapes the ring preview borrows, in the order the real launcher ring uses them.
const PREVIEW_SHAPES = ['splitArc', 'sensor', 'scanner', 'reticle'];
const PREVIEW_TABS = ['W3ATH3R', 'C4L3ND4R'];

const RingsPreview = () => (
  <div className="flex items-center justify-center gap-3">
    {PREVIEW_SHAPES.map((shape, index) => (
      <HudRing key={shape} shape={shape} state={index === 0 ? 'active' : 'idle'} size={28} />
    ))}
  </div>
);

const TabsPreview = () => (
  <div className="flex items-center justify-center gap-6">
    {PREVIEW_TABS.map((label) => (
      <div
        key={label}
        className="relative bg-fui-panel border border-fui-border w-[20px] h-[72px] flex items-center justify-center"
      >
        <div className="absolute -top-px -right-px w-2 h-2 border-t border-r border-fui-accent" />
        <div className="absolute -bottom-px -right-px w-2 h-2 border-b border-r border-fui-accent" />
        <span
          className="text-fui-accent font-tech font-bold text-[9px] uppercase tracking-widest"
          style={{ writingMode: 'vertical-rl', textOrientation: 'mixed', whiteSpace: 'nowrap' }}
        >
          {label}
        </span>
      </div>
    ))}
  </div>
);

const PREVIEWS = { rings: RingsPreview, tabs: TabsPreview };

const NexusNavCustomization = () => {
  const { nexusNav, setNexusNav } = useUiPrefs();

  return (
    <div>
      <div className="mb-4 flex items-start space-x-2">
        <LayoutTemplate className="w-5 h-5 text-fui-accent mt-0.5" />
        <div>
          <h3 className="font-tech font-bold text-lg uppercase tracking-widest text-fui-accent">
            Nexus Navigation
          </h3>
          <p className="text-fui-text text-xs">
            Pick how the Nexus side panels are opened. Changes apply immediately and persist
            across sessions.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {NEXUS_NAV_MODES.map((mode, index) => {
          const detail = NAV_DETAILS[mode];
          const active = nexusNav === mode;
          const Preview = PREVIEWS[mode];
          return (
            <motion.button
              key={mode}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1, duration: 0.3 }}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => setNexusNav(mode)}
              aria-pressed={active}
              className={`relative text-left bg-fui-panel border font-mono transition-all duration-300 ${
                active ? 'border-fui-accent' : 'border-fui-border hover:border-fui-accent/60'
              }`}
              style={{
                boxShadow: active
                  ? `0 0 20px color-mix(in srgb, var(--theme-tactical-accent) 40%, transparent)`
                  : undefined,
              }}
            >
              <div className="flex h-24 items-center justify-center border-b border-fui-border bg-fui-bg">
                <Preview />
              </div>
              <div className="p-4">
                <div className="flex items-center justify-between">
                  <span className="text-fui-accent font-bold uppercase tracking-wider">
                    {detail.label}
                  </span>
                  {active && <Check className="w-4 h-4 text-fui-accent" />}
                </div>
                <p className="mt-1 text-fui-text text-xs leading-relaxed">{detail.description}</p>
              </div>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
};

export default NexusNavCustomization;
