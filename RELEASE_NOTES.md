# Release v0.2.0

## Release Name: Multi-Camera Registry

### Notes:
- **Feature:** Camera streaming now reads from the device registry instead of a single global `STREAM_CAMERA_URL` env var — any device with `device_type = 'camera'` and a `stream_url` set (via Domain → Devices) can be streamed, and the Nexus camera panel lets you select/toggle between all configured cameras.
- **Feature:** Added ESPHome as a local-only, always-on IoT provider (mDNS discovery + Noise-encrypted native API), running in parallel with whichever of Home Assistant/SmartThings is set as the default provider.
- **Fix:** Camera stream panel showing "stream unavailable"/a black rectangle — nginx's CSP had no `media-src` directive, so `blob:` URLs (used by hls.js for playback) fell back to the `default-src 'self'` policy and were blocked.
- **Security:** `stream_url` (which embeds RTSP credentials) is write-only through the API — `GET /api/devices` and its websocket broadcast only ever expose a `has_stream` boolean, never the raw URL.

# Release v0.1.8

## Release Name: Situational Awareness Registry

### Notes:
- **Feature:** Situational-awareness engine rebuilt around a rule registry (`DISPLAY_RULES` in `alfr3ddaemon.py`) instead of a fixed check list, so new card types register without hardcoding their slot.
- **Feature:** Added `mood` (ambient day/time energy read), `focus_needed` (heads-up when a call-like event is starting soon), and `weather_advisory` (forward-looking rain warning) cards.
- **Feature:** Added a `travel` card with leave-by time and estimated fuel cost for the next address-bearing calendar event, via the Google Maps Directions API; falls back to no travel card (event still shows as a plain listing) when a destination, API key, or route can't be resolved.
- **Feature:** Real OpenWeatherMap forecast integration (`get_forecast()`) backing the new rain advisory, replacing the prior stub.
- **Fix:** Card display cap now tracks the number of registered rules instead of a hardcoded slice, which previously could silently drop lower-priority cards (e.g. weather) once enough higher-priority cards fired in the same cycle. Frontend cap kept in sync with the backend registry size.

# Release v0.1.3

## Release Name: WebSockets Support

### Notes:
- **Feature:** Added WebSockets support (PR #44).
- **Security:** Updated dependencies to address security issues.
- **Dependencies:** Bumped various dependencies for improved performance and security.
