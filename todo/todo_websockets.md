# Plan to Change Frontend from Polling to WebSockets for Kafka Messages

## Current State
- Frontend polls `/api/events` (every 5s) and `/api/situational-awareness` (every 60s) using `setInterval`.
- Backend stores recent Kafka messages in memory and serves via REST endpoints.

## Implementation Plan
1. **Backend Updates**:
   - Add `flask-socketio` and `python-socketio` to `services/service_api/requirements.txt`.
   - Initialize SocketIO in `app.py`, emit events to clients on Kafka message receipt.
   - Replace `app.run()` with `socketio.run()`.

2. **Frontend Updates**:
   - Add `socket.io-client` to `package.json`.
   - Replace polling in `EventStream.jsx`, `SituationalAwareness.jsx`, and `AudioPlayer.jsx` with WebSocket listeners.
   - Add fallback API calls for initial load.

3. **Configuration**:
   - Update `.env` for WebSocket URL (e.g., `VITE_WS_BASE_URL`).
   - Ensure Docker Compose exposes ports.

4. **Testing**:
   - Build with `docker-compose up --build`.
   - Verify real-time updates and backward compatibility.

## Challenges
- WebSocket reconnections, scalability for many clients, security (CORS restrictions).
