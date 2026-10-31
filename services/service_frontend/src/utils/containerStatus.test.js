import { describe, it, expect } from 'vitest';
import { containerStatus, statusTier, STATUS } from './containerStatus';

describe('containerStatus', () => {
  it('reports a clean on-demand exit as IDLE, in the ok tier', () => {
    const tls = { name: 'alfr3d-service-tls-1', state: 'exited', health: 'none', idle: true };
    expect(containerStatus(tls)).toBe(STATUS.IDLE);
    expect(statusTier(tls)).toBe('ok');
  });

  it('still reports any other exited container as DOWN', () => {
    expect(containerStatus({ state: 'exited', health: 'none' })).toBe(STATUS.DOWN);
    expect(containerStatus({ state: 'exited', health: 'none', idle: false })).toBe(STATUS.DOWN);
  });

  it('keeps the existing verdicts for running containers', () => {
    expect(containerStatus({ state: 'running', health: 'healthy' })).toBe(STATUS.NOMINAL);
    expect(containerStatus({ state: 'running', health: 'unhealthy' })).toBe(STATUS.CRITICAL);
    expect(containerStatus({ state: 'restarting', health: 'none' })).toBe(STATUS.CRITICAL);
  });
});
