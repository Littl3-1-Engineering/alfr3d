import { motion } from 'framer-motion';
import PropTypes from 'prop-types';

// Animated weather icon rendered from the OWM description + day/night state.
// Self-contained animated SVGs (no external Lottie assets). Colors follow the
// theme tokens: sun = env yellow, clouds = slate, rain = cyan primary.

const SUN = 'var(--theme-env)';
const CLOUD = 'var(--theme-text-tertiary)';
const CLOUD_DIM = 'var(--theme-text-tertiary)';
const RAIN = 'var(--theme-primary)';
const SNOW = 'var(--theme-text-secondary)';
const BOLT = 'var(--theme-warning)';
const MOON = 'var(--theme-text-secondary)';

const sunRays = (accent) => Array.from({ length: 8 }).map((_, i) => {
  const angle = (i * 45 * Math.PI) / 180;
  const x1 = Math.cos(angle) * 22;
  const y1 = Math.sin(angle) * 22;
  const x2 = Math.cos(angle) * 30;
  const y2 = Math.sin(angle) * 30;
  return (
    <motion.line
      key={i}
      x1={50 + x1}
      y1={50 + y1}
      x2={50 + x2}
      y2={50 + y2}
      stroke={accent}
      strokeWidth="3"
      strokeLinecap="round"
      initial={{ opacity: 0.6, scale: 0.85 }}
      animate={{ opacity: [0.4, 1, 0.4], scale: [0.85, 1.1, 0.85] }}
      transition={{ duration: 2.4, repeat: Infinity, delay: i * 0.15, ease: 'easeInOut' }}
      transform={`rotate(${i * 45} 50 50)`}
    />
  );
});

const cloudPath = 'M30 70 a9 9 0 0 1 0-18 a12 12 0 0 1 23-4 a9 9 0 0 1 17 10 a11 11 0 0 1 -5 21 h-34 z';

const ClearIcon = () => (
  <g>
    {sunRays(SUN)}
    <motion.circle
      cx="50" cy="50" r="16"
      fill={SUN}
      animate={{ scale: [1, 1.08, 1] }}
      transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
      style={{ transformOrigin: '50px 50px' }}
    />
  </g>
);

const ClearNightIcon = () => (
  <g>
    {[
      [20, 24, 1.6], [78, 18, 1], [84, 40, 0.8], [16, 66, 1.2], [70, 74, 1],
    ].map(([cx, cy, o], i) => (
      <motion.circle
        key={i}
        cx={cx} cy={cy} r="2"
        fill={SNOW}
        opacity={o}
        animate={{ opacity: [o, o * 0.2, o] }}
        transition={{ duration: 2.2, repeat: Infinity, delay: i * 0.35 }}
      />
    ))}
    <motion.path
      d="M62 28 a20 20 0 1 0 0 34 a17 17 0 0 1 0 -34 z"
      fill={MOON}
      animate={{ rotate: [0, -6, 0] }}
      transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
      style={{ transformOrigin: '50px 50px' }}
    />
  </g>
);

const CloudIcon = ({ offset = 0, opacity = 1 }) => (
  <motion.path
    d={cloudPath}
    fill={CLOUD}
    opacity={opacity}
    animate={{ x: [offset, offset + 6, offset] }}
    transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut' }}
  />
);

CloudIcon.propTypes = {
  offset: PropTypes.number,
  opacity: PropTypes.number,
};

const PartlyCloudyIcon = () => (
  <g>
    <g>{sunRays(SUN)}</g>
    <motion.circle cx="38" cy="38" r="13" fill={SUN} style={{ transformOrigin: '38px 38px' }} />
    <CloudIcon offset={-4} opacity={0.95} />
  </g>
);

const RainIcon = () => (
  <g>
    <CloudIcon offset={0} opacity={0.95} />
    {[0, 1, 2, 3].map((i) => (
      <motion.line
        key={i}
        x1={30 + i * 12}
        y1={72}
        x2={26 + i * 12}
        y2={82}
        stroke={RAIN}
        strokeWidth="3"
        strokeLinecap="round"
        initial={{ opacity: 0 }}
        animate={{ opacity: [0, 1, 1, 0], y: [0, 2, 4, 6] }}
        transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.18 }}
      />
    ))}
  </g>
);

const SnowIcon = () => (
  <g>
    <CloudIcon offset={0} opacity={0.95} />
    {[0, 1, 2, 3].map((i) => (
      <motion.circle
        key={i}
        cx={28 + i * 14}
        cy={74}
        r="2.4"
        fill={SNOW}
        initial={{ opacity: 0 }}
        animate={{ opacity: [0, 1, 1, 0], y: [0, 3, 6, 9], x: [0, -2, 2, 0] }}
        transition={{ duration: 1.4, repeat: Infinity, delay: i * 0.3 }}
      />
    ))}
  </g>
);

const ThunderIcon = () => (
  <g>
    <CloudIcon offset={0} opacity={0.9} />
    <motion.path
      d="M52 72 L44 84 L50 84 L45 96 L58 80 L51 80 L56 72 z"
      fill={BOLT}
      animate={{ opacity: [0, 1, 1, 0, 1] }}
      transition={{ duration: 1.6, repeat: Infinity, times: [0, 0.3, 0.5, 0.7, 1] }}
    />
  </g>
);

const FogIcon = () => (
  <g>
    <CloudIcon offset={0} opacity={0.55} />
    {[0, 1, 2].map((i) => (
      <motion.line
        key={i}
        x1={22 + i * 4}
        y1={70 + i * 8}
        x2={78 - i * 4}
        y2={70 + i * 8}
        stroke={CLOUD_DIM}
        strokeWidth="3.5"
        strokeLinecap="round"
        animate={{ x: [0, 5, 0] }}
        transition={{ duration: 5 + i, repeat: Infinity, ease: 'easeInOut', delay: i * 0.4 }}
      />
    ))}
  </g>
);

// Map an OWM description string to an icon variant.
const getWeatherVariant = (description = '', isNight = false) => {
  const d = (description || '').toLowerCase();
  if (d.includes('thunder')) return 'thunder';
  if (d.includes('snow') || d.includes('sleet') || d.includes('ice')) return 'snow';
  if (d.includes('rain') || d.includes('drizzle') || d.includes('shower')) return 'rain';
  if (d.includes('fog') || d.includes('mist') || d.includes('haze') || d.includes('smoke') || d.includes('dust')) return 'fog';
  if (d.includes('few clouds') || d.includes('scattered') || d.includes('partly')) return 'partly-cloudy';
  if (d.includes('cloud') || d.includes('overcast')) return 'cloudy';
  if (d.includes('clear') || !d) return isNight ? 'clear-night' : 'clear';
  return isNight ? 'clear-night' : 'partly-cloudy';
};

const WeatherIcon = ({ description = '', isNight = false, className = '' }) => {
  const variant = getWeatherVariant(description, isNight);
  const icons = {
    clear: ClearIcon,
    'clear-night': ClearNightIcon,
    'partly-cloudy': PartlyCloudyIcon,
    cloudy: CloudIcon,
    rain: RainIcon,
    snow: SnowIcon,
    thunder: ThunderIcon,
    fog: FogIcon,
  };
  const Icon = icons[variant] || ClearIcon;

  return (
    <div className={className} aria-label={`Weather: ${variant}`}>
      <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-lg">
        <Icon />
      </svg>
    </div>
  );
};

WeatherIcon.propTypes = {
  description: PropTypes.string,
  isNight: PropTypes.bool,
  className: PropTypes.string,
};

export default WeatherIcon;
