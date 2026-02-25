# Plan to Change Frontend from Polling to WebSockets for Kafka Messages

## Current State
- Frontend polls `/api/events` (every 5s) and `/api/situational-awareness` (every 60s) using `setInterval`.
- Backend stores recent Kafka messages in memory and serves via REST endpoints.

## Implementation Plan
1. **Backend Updates** (DONE):
   - [x] Add `flask-socketio`, `python-socketio`, and `eventlet` to `services/service_api/requirements.txt`.
   - [x] Initialize SocketIO on separate port (5002), emit events to clients on Kafka message receipt.
   - [x] Run Flask REST API on port 5001, SocketIO server on port 5002 (background thread).
   - [x] Keep REST endpoints for fallback (see Future Work below).

2. **Frontend Updates** (DONE):
   - [x] Add `socket.io-client` to `package.json`.
   - [x] Create `src/utils/socket.js` for shared socket connection.
   - [x] Replace polling in `EventStream.jsx`, `SituationalAwareness.jsx`, and `AudioPlayer.jsx` with WebSocket listeners.
   - [x] Add fallback API calls for initial load only.

3. **Configuration** (DONE):
   - [x] Add `VITE_WS_BASE_URL` to `.env.example` (defaults to `window.location.origin`).
   - [x] Expose port 5002 in Docker Compose for SocketIO.

4. **Nginx Configuration** (DONE):
   - [x] Route `/api/` to port 5001 (REST API).
   - [x] Route `/ws/` to port 5002 (SocketIO).
   - [x] Add WebSocket upgrade support.

5. **Testing** (DONE):
   - [x] Build with `docker-compose up --build`.
   - [x] Verify real-time updates and backward compatibility.

## Future Work
- **Remove polling fallback**: After WebSocket implementation is stable:
  - Remove REST endpoints `/api/events` and `/api/situational-awareness` from `service_api/app.py`
  - Remove all `setInterval` polling code from frontend components
  - Only keep WebSocket connection (remove fallback API calls)

## Challenges
- WebSocket reconnections, scalability for many clients, security (CORS restrictions).
