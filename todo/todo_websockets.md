# Real-Time WebSocket Implementation Status

## Current State

### Backend Background Tasks (all broadcast via WebSocket)

| Event | Source | Interval |
|-------|--------|----------|
| `events` | Kafka `event-stream` consumer | ~100ms poll |
| `situational_awareness` | Kafka `situational-awareness` consumer | ~100ms poll |
| `containers` | `collect_container_metrics()` | 10s |
| `users` | `broadcast_users()` | 5s |
| `devices` | `broadcast_devices()` | 10s |
| `iot_devices` | `broadcast_iot_devices()` | 30s |
| `calendar_events` | `broadcast_calendar_events()` | 300s |
| `project_tree` | File watcher (`tree_of_alfr3d.py`) | 10s (on change) |

### WebSocket Events Also Emitted on Demand
- `users` — Emitted on every `GET /api/users` response
- `devices` — Emitted on every `GET /api/devices` response
- `iot_devices` — Emitted after IoT device control, link, or unlink
- `weather` — Emitted on every `GET /api/weather` response
- `environment` — Emitted on every `GET /api/environment` response

### Components Using WebSocket (no polling)

| Component | Events Subscribed |
|-----------|------------------|
| **EventStream.jsx** | `events` |
| **SituationalAwareness.jsx** | `situational_awareness` |
| **AudioPlayer.jsx** | `events` |
| **ContainerHealth.jsx** | `containers` |
| **Core.jsx (Dashboard)** | `containers`, `users`, `devices` |
| **System.jsx** | `containers`, `events` |
| **Personality.jsx** | `personality_state` |
| **ProjectTreeViz.jsx** | `project_tree` |
| **OnlineUsers.jsx** | `users` |
| **GuestRoster.jsx** | `users` |
| **LocationPanel.jsx** | `environment` |
| **WeatherPanel.jsx** | `weather` |
| **CalendarPanel.jsx** | `calendar_events` |
| **Blueprint.jsx** | `devices`, `iot_devices` |
| **DeviceRegistry.jsx** | `devices`, `iot_devices` |

### HTTP Polling Removed
All components previously using HTTP polling were migrated to WebSocket:

| Component | Old Poll Interval | Former Endpoint | Migration |
|-----------|------------------|-----------------|-----------|
| **CalendarPanel.jsx** | 5 min | `/api/calendar/events` | New `broadcast_calendar_events()` background task + `calendar_events` WS event |
| **WeatherPanel.jsx** | 10 min | `/api/weather` | Backend already broadcasts on GET; initial fetch kept for hydration |
| **LocationPanel.jsx** | 1 min | `/api/environment` | Backend already broadcasts on GET; initial fetch kept for hydration |
| **AudioPlayer.jsx** | 30s | `/api/events` | Kafka consumer already broadcasts via `events` WS event; initial fetch removed |

## WebSocket Architecture

- **Endpoint:** `ws://{host}/ws`
- **Message format:** `{"event": "<event_type>", "data": <payload>}`
- **Client:** Singleton `SocketClient` in `utils/socket.js` with auto-reconnect (5 attempts, 1s delay)
- **Backend:** `ConnectionManager` in `dependencies.py` with `broadcast(event, data)` method
