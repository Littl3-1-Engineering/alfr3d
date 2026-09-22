// How the Nexus side panels are opened. The HUD launcher ring replaced the vertical-text
// edge tabs outright on 2026-09-20; this makes the tabs a choice again rather than a
// rollback, so the ring stays the default and nobody is stuck with a silhouette they
// would rather read as a label.
//
//   'rings' — the launcher ring around the Core
//   'tabs'  — the edge tabs the ring replaced
//
// This list is the source of truth for which modes exist AND the order they are offered
// in; the customization cards render straight off it.
export const NEXUS_NAV_MODES = ['rings', 'tabs'];
export const defaultNexusNav = 'rings';
export const NEXUS_NAV_STORAGE_KEY = 'alfr3d-nexus-nav';
