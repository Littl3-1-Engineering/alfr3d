# Plan: Tree of ALFR3D - Project Tree Visualization

## Overview
Animated D3.js force-directed tree visualization of the ALFR3D project structure, embedded as a panel in the Nexus dashboard.

## Files to Create/Modify

| File | Action |
|------|--------|
| `services/service_api/tree_of_alfr3d.py` | **CREATE** - Tree generation module |
| `services/service_api/app.py` | **MODIFY** - Register blueprint/routes |
| `services/service_frontend/src/components/ProjectTreeViz.jsx` | **CREATE** - D3 visualization |
| `services/service_frontend/src/pages/Nexus.jsx` | **MODIFY** - Add panel |
| `services/service_frontend/index.html` | **MODIFY** - Add D3 CDN + Orbitron font |

## Backend: tree_of_alfr3d.py

### Dependencies
- Already in service_api: `flask`, `flask_socketio`, `os`, `logging`

### Core Functions
```
scan_directory(path, root_name) -> dict
- Recursively scan directories
- Respect .gitignore patterns
- Return: { "name": str, "children": [...] } for dirs
- Return: { "name": str, "size": int } for files
```

### Exclusions (from .gitignore)
- `__pycache__/`, `.env`, `*.pyc`, `.pytest_cache/`, `.venv/`, `node_modules/`, `dist/`, `backup/`, `.git/`

### API Endpoints
- `GET /api/project-tree` - Returns JSON tree
- SocketIO event `project_tree` - Broadcast on file changes

### File Watching (for WebSocket)
- Use polling (simpler, no new deps) or `watchdog` library
- Emit SocketIO event when tree structure changes

---

## Frontend: ProjectTreeViz.jsx

### D3.js Implementation
- **Layout**: Force-directed tree using `d3.forceSimulation`
- **Forces**:
  - `d3.forceLink()` - Parent-child connections
  - `d3.forceManyBody()` - Node repulsion
  - `d3.forceCenter()` - Center in container
  - **Custom wind force**: `Math.sin(time + depth * 0.5) * amplitude` for gentle swaying

### Visual Design
| Element | Color/Style |
|---------|-------------|
| Background | `#0A0F1E` (dark charcoal) |
| Branches/Links | `#00FFFF` (cyan) with varying opacity |
| Folder Nodes | `#00FFFF` (cyan) with glow |
| File Leaves | `#FFD700` (warm yellow) |
| Font | Orbitron (Google Fonts) |

### Glassmorphism
- Container: `backdrop-filter: blur(5px)`, `background: rgba(10, 15, 30, 0.7)`
- Border: `box-shadow: 0 0 10px #00FFFF`

### Animations
- **Sway**: 60fps via `requestAnimationFrame`, sine wave oscillation
- **Pulse**: Active service nodes (match against container names) pulse faintly

### Interactivity
- **Hover**: Tooltip showing path + file size
- **Click**: Toggle expand/collapse children

### Container
- `#project-viz-panel`: 400x300px
- Embed in Nexus grid or collapsible side panel

---

## Integration in Nexus.jsx

```jsx
import ProjectTreeViz from '../components/ProjectTreeViz';

// Add to side panel or grid:
<TacticalPanelVariant2 title="Pr0j3ct Tr33">
  <ProjectTreeViz />
</TacticalPanelVariant2>
```

---

## WebSocket Flow
1. Backend watches project directory (polling or watchdog)
2. On change → regenerate tree → emit `project_tree` via SocketIO
3. Frontend receives event → fetches `/api/project-tree` → updates D3

---

## Acceptance Criteria
- [ ] Tree displays full project structure (excluding gitignore patterns)
- [ ] Gentle swaying animation at 60fps
- [ ] Cyan glowing nodes, yellow file leaves
- [ ] Glassmorphism styling with blur effect
- [ ] Hover shows tooltip with path/size
- [ ] Click expands/collapses nodes
- [ ] Real-time updates via WebSocket
- [ ] Fetches data on component mount
- [ ] Works in 400x300px panel
