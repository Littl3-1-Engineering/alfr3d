// Container health is Docker's own verdict, not a resource-utilization score. Deriving
// health from CPU/memory says "busy = dying", which is backwards for a broker: a Kafka
// healthcheck burst used to render as 0%/CRITICAL purely for doing its job.
//
// `state` is the lifecycle (running/restarting/exited/paused/dead) and `health` is the
// healthcheck verdict. `health: 'none'` means the container declares no healthcheck --
// most alfr3d services don't -- so "running" is the strongest claim we can honestly make.

export const STATUS = {
  NOMINAL: 'NOMINAL',
  STARTING: 'STARTING',
  DEGRADED: 'DEGRADED',
  CRITICAL: 'CRITICAL',
  DOWN: 'DOWN',
};

// Severity tiers, worst last -- Core sizes its orbit dots by this ordering.
const TIER = {
  [STATUS.NOMINAL]: 'ok',
  [STATUS.STARTING]: 'warn',
  [STATUS.DEGRADED]: 'warn',
  [STATUS.CRITICAL]: 'bad',
  [STATUS.DOWN]: 'bad',
};

export const containerStatus = (container = {}) => {
  const state = container.state;
  const health = container.health;

  if (state === 'exited' || state === 'dead') return STATUS.DOWN;
  if (state === 'restarting') return STATUS.CRITICAL;
  if (health === 'unhealthy') return STATUS.CRITICAL;
  if (health === 'starting') return STATUS.STARTING;
  if (state === 'paused') return STATUS.DEGRADED;
  if (state === 'running') return STATUS.NOMINAL;
  return STATUS.DEGRADED; // unknown state: not provably fine, not provably broken
};

export const statusTier = (container) => TIER[containerStatus(container)];

export const statusColor = (container) => {
  const tier = statusTier(container);
  if (tier === 'ok') return 'var(--theme-success)';
  if (tier === 'warn') return 'var(--theme-warning)';
  return 'var(--theme-error)';
};

// What the bar actually measures now: headline resource utilization, not "health".
export const utilization = (container = {}) =>
  Math.min(100, Math.max(0, Math.max(container.cpu ?? 0, container.mem ?? 0)));
