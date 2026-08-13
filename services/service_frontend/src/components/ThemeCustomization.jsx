import { motion } from 'framer-motion';
import { Check, Palette } from 'lucide-react';
import { useTheme } from '../utils/useTheme';
import { themes } from '../utils/themes';

const THEME_DETAILS = {
  dark: {
    label: 'Cyan / Navy',
    description: 'Deep navy substrate with glowing cyan accents. The default ALFR3D look.',
  },
  amber: {
    label: 'Amber / Charcoal',
    description: 'Ultra-deep charcoal with electric amber highlights and steel-blue secondary.',
  },
  light: {
    label: 'Light / Teal',
    description: 'Whites and grays with teal primary and red secondary highlights.',
  },
};

const ThemeCustomization = () => {
  const { currentTheme, setCurrentTheme } = useTheme();

  return (
    <div>
      <div className="mb-4 flex items-start space-x-2">
        <Palette className="w-5 h-5 text-fui-accent mt-0.5" />
        <div>
          <h3 className="font-tech font-bold text-lg uppercase tracking-widest text-fui-accent">
            UI Theme
          </h3>
          <p className="text-fui-text text-xs">
            Pick a theme. Changes apply immediately and persist across sessions.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {Object.keys(THEME_DETAILS).map((key, index) => {
          const theme = themes[key];
          const detail = THEME_DETAILS[key];
          const active = currentTheme === key;
          return (
            <motion.button
              key={key}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1, duration: 0.3 }}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => setCurrentTheme(key)}
              aria-pressed={active}
              className={`relative text-left bg-fui-panel border font-mono transition-all duration-300 ${
                active
                  ? 'border-fui-accent'
                  : 'border-fui-border hover:border-fui-accent/60'
              }`}
              style={{
                boxShadow: active
                  ? `0 0 20px color-mix(in srgb, var(--theme-tactical-accent) 40%, transparent)`
                  : undefined,
              }}
            >
              <div
                className="flex h-24 items-center justify-center gap-3 border-b border-fui-border"
                style={{ background: theme.tactical.bg }}
              >
                <span
                  className="w-8 h-8 rounded-full"
                  style={{
                    background: theme.tactical.accent,
                    boxShadow: `0 0 12px ${theme.glow}`,
                  }}
                />
                <span
                  className="w-8 h-8 rounded-full border border-fui-border"
                  style={{ background: theme.secondary }}
                />
                <span
                  className="w-8 h-8 rounded-full"
                  style={{ background: theme.tactical.panel, border: `1px solid ${theme.tactical.border}` }}
                />
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

export default ThemeCustomization;
