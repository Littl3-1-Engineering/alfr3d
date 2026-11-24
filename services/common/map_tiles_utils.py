"""Is the dashboard's map basemap still serving real map tiles? (`check_system_health` probe.)

The Location panel loads its tiles straight from a third party in the browser, so the backend
never sees them. When CARTO began requiring an API key it kept answering HTTP 200 -- with a PNG
that has "API KEY REQUIRED" painted across it -- so the map silently turned into a watermark and
nothing on the dashboard said why. A status-code check can't catch that; this fetches one fixed,
dense tile and checks that it looks like a map rather than an error placeholder.

Esri's World Dark Gray basemap serves real tiles as JPEG; its "no data" and error placeholders
are PNG, and a real city tile is tens of KB. Both are checked, so either kind of failure trips.

Keep `MAP_TILE_PROBE_URL` in step with the URL in `LocationPanel.jsx` (same provider and path;
the z/y/x here is lower Manhattan, chosen because it is covered at every zoom and never blank).
"""

import logging

import requests

logger = logging.getLogger(__name__)

MAP_TILE_PROBE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base"
    "/MapServer/tile/15/12320/9647"
)
TIMEOUT_S = 10
# A real dense-city tile is ~19 KB; the placeholders are ~2 KB. Well clear of both.
MIN_REAL_TILE_BYTES = 6000
JPEG_MAGIC = b"\xff\xd8\xff"


def is_map_tiles_configured():
    """The basemap is always in use, so it is always probed."""
    return True


def test_map_tiles():
    """(ok, message). A network error, non-200, non-JPEG or tiny body all count as failing."""
    try:
        response = requests.get(
            MAP_TILE_PROBE_URL,
            headers={"User-Agent": "Alfr3d-HomeButler/1.0 (map tile health probe)"},
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as e:
        return False, f"tile request failed: {e}"

    if response.status_code != 200:
        return False, f"tile server answered HTTP {response.status_code}"
    body = response.content
    if not body.startswith(JPEG_MAGIC):
        return False, "tile is not a JPEG map image (likely an error/watermark placeholder)"
    if len(body) < MIN_REAL_TILE_BYTES:
        return False, f"tile is only {len(body)} bytes (likely a placeholder)"
    return True, "OK"
