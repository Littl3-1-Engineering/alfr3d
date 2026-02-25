# Plan to Implement Controls for All Smarthome Devices

## Current State
- `service_device` only discovers devices; no control capabilities.
- Database tracks basic device info but lacks capabilities or commands.

## Implementation Plan
1. **Architecture**:
   - Add `service_smarthome` microservice for device control.
   - Support protocols: Wi-Fi (Tuya, Philips Hue, TP-Link), Zigbee/Z-Wave (via hubs), Matter.
   - Extend DB with `device_capabilities`, `device_commands`, `smarthome_integrations`.

2. **Backend**:
   - Create protocol adapters (e.g., `adapters/hue.py` using libraries like `pyhue`).
   - Add API endpoints: `POST /api/devices/{id}/control`, `GET /api/devices/{id}/capabilities`.
   - Use Kafka for commands/status updates.

3. **Frontend**:
   - Add control widgets (toggles, sliders) in React dashboard.
   - Integrate with WebSockets for real-time status.

4. **Security**:
   - JWT auth, role-based access, encrypted credentials, audit logging.

5. **Setup & Testing**:
   - Update Docker/K8s manifests.
   - Add onboarding wizard for hub pairing.
   - Test with mocks; lint and deploy.

## Challenges
- Protocol diversity, hub dependencies, local vs. cloud control.
