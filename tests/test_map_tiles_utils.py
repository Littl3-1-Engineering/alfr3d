"""common.map_tiles_utils: the basemap probe must reject the placeholders a provider serves."""

from unittest.mock import MagicMock, patch

import requests

from services.common import map_tiles_utils as m

REAL_TILE = b"\xff\xd8\xff" + b"x" * 19000
CARTO_STYLE_WATERMARK = b"\x89PNG\r\n\x1a\n" + b"x" * 2500  # HTTP 200, PNG, ~2.5 KB


def _response(status=200, body=REAL_TILE):
    r = MagicMock()
    r.status_code = status
    r.content = body
    return r


def _probe(**kwargs):
    with patch.object(m.requests, "get", return_value=_response(**kwargs)):
        return m.test_map_tiles()


def test_real_jpeg_tile_passes():
    assert _probe() == (True, "OK")


def test_watermark_png_with_http_200_fails():
    """The failure that went unnoticed: a 200 whose body is an 'API KEY REQUIRED' image."""
    ok, message = _probe(body=CARTO_STYLE_WATERMARK)
    assert ok is False
    assert "placeholder" in message


def test_tiny_jpeg_fails():
    ok, _ = _probe(body=b"\xff\xd8\xff" + b"x" * 500)
    assert ok is False


def test_non_200_fails():
    ok, message = _probe(status=403)
    assert ok is False
    assert "403" in message


def test_network_error_fails():
    with patch.object(m.requests, "get", side_effect=requests.ConnectionError("dns")):
        ok, message = m.test_map_tiles()
    assert ok is False
    assert "dns" in message


def test_probe_url_matches_the_frontend_provider():
    """Keep the probe on the same provider LocationPanel.jsx renders."""
    import pathlib

    jsx = (
        pathlib.Path(__file__).resolve().parents[1]
        / "services/service_frontend/src/components/LocationPanel.jsx"
    ).read_text()
    host_and_path = m.MAP_TILE_PROBE_URL.split("/MapServer/")[0]
    assert host_and_path in jsx
