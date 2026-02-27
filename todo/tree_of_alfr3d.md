# Plan: Tree of ALFR3D - Project Tree Visualization

## Overview
Animated D3.js force-directed tree visualization of the ALFR3D project structure, embedded as a panel in the Nexus dashboard.

## Implementation Complete ✓

### Files Created/Modified

| File | Action | Status |
|------|--------|--------|
| `services/service_api/tree_of_alfr3d.py` | CREATE - Tree generation module | ✓ Complete |
| `services/service_api/app.py` | MODIFY - Register blueprint/routes | ✓ Complete |
| `services/service_api/Dockerfile` | MODIFY - Copy tree_of_alfr3d.py | ✓ Complete |
| `services/service_frontend/src/components/ProjectTreeViz.jsx` | CREATE - D3 visualization | ✓ Complete |
| `services/service_frontend/src/pages/Nexus.jsx` | MODIFY - Add panel | ✓ Complete |
| `services/service_frontend/index.html` | MODIFY - Add D3 CDN + Orbitron font | ✓ Complete |
| `services/service_frontend/package.json` | MODIFY - Add d3 dependency | ✓ Complete |
| `services/service_frontend/Dockerfile` | MODIFY - Upgrade to Node 20 | ✓ Complete |
| `docker-compose.yml` | MODIFY - Add volume mount for project | ✓ Complete |

### Implementation Details

#### Backend: tree_of_alfr3d.py
- Flask blueprint with `scan_directory()` function
- Excludes: `__pycache__/`, `.env`, `*.pyc`, `.pytest_cache/`, `.venv/`, `node_modules/`, `dist/`, `backup/`, `.git/`, etc.
- `GET /api/project-tree` endpoint returns JSON tree
- Polling file watcher (10s interval) broadcasts changes via SocketIO
- Lazy initialization of cached tree for proper module loading

#### Frontend: ProjectTreeViz.jsx
- D3.js force-directed tree with:
  - `d3.forceLink()` - Parent-child connections
  - `d3.forceManyBody()` - Node repulsion
  - `d3.forceCenter()` - Center in container
  - Custom wind force: `Math.sin(time + depth * 0.5) * amplitude` for swaying
- Visual design:
  - Background: `rgba(10, 15, 30, 0.7)` with backdrop blur
  - Links: `#00FFFF` (cyan) with varying opacity
  - Folder nodes: `#00FFFF` (cyan) with glow effect
  - File leaves: `#FFD700` (warm yellow)
  - Font: Orbitron
- Glassmorphism container styling
- Hover tooltip with path + file size
- Click to expand/collapse nodes
- Real-time updates via SocketIO

#### Integration in Nexus.jsx
- Added collapsible side panel on right side
- Panel title: "PR0J3CT TR33"
- Uses TacticalPanelVariant2 for styling

#### Infrastructure Changes
- Volume mount: `.:/project:ro` in docker-compose.yml for service-api
- Node.js upgraded from 18 to 20 (Vite 7.x requirement)
- Added d3@^7.9.0 to package.json

---

## Pending Tasks

### High Priority
- [ ] **Increase panel size significantly** - Current 300px height is too small; expand to fill more of the screen
- [ ] **Style panel consistently** - Match TacticalPanelVariant styling (corner markers, header bar, borders, colors, background)

### Medium Priority
- [ ] Add search/filter functionality to find files quickly
- [ ] Add zoom controls (zoom in/out/reset buttons)
- [ ] Optimize for large directories (virtualization or level limits)

---

## Acceptance Criteria

- [x] Tree displays full project structure (excluding gitignore patterns)
- [x] Gentle swaying animation at 60fps
- [x] Cyan glowing nodes, yellow file leaves
- [x] Glassmorphism styling with blur effect
- [x] Hover shows tooltip with path/size
- [x] Click expands/collapses nodes
- [x] Real-time updates via WebSocket (polling every 10s)
- [x] Fetches data on component mount
- [x] Works in collapsible side panel
