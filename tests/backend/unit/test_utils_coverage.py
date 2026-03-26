import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.utils import geocode_location, clean_html_tags
from backend.providers.jobs.models import Coordinates

@pytest.mark.asyncio
async def test_geocode_location_nominatim_success():
    """Test successful geocoding via Nominatim fallback."""
    # Ensure cache is clear for this test
    from collections import OrderedDict
    with patch("backend.services.utils._geocode_cache", OrderedDict()):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"lat": "46.5", "lon": "6.5"}]
        
        async def mock_get(*args, **kwargs):
            return mock_resp

        with patch("httpx.AsyncClient.get", side_effect=mock_get):
            coords = await geocode_location("MockCity")
            assert coords.lat == 46.5
            assert coords.lon == 6.5

@pytest.mark.asyncio
async def test_geocode_location_nominatim_failure():
    """Test geocoding failure (Nominatim returns 404 or empty)."""
    from collections import OrderedDict
    with patch("backend.services.utils._geocode_cache", OrderedDict()):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        
        async def mock_get(*args, **kwargs):
            return mock_resp

        with patch("httpx.AsyncClient.get", side_effect=mock_get):
            coords = await geocode_location("NonExistentCity")
            assert coords is None

@pytest.mark.asyncio
async def test_geocode_location_exception():
    """Test geocoding resilience when network error occurs."""
    with patch("backend.services.utils._geocode_cache", {}):
        with patch("httpx.AsyncClient.get", side_effect=httpx.RequestError("Network Down")):
            coords = await geocode_location("FailingCity")
            assert coords is None

def test_clean_html_tags_empty():
    assert clean_html_tags("") == ""
    assert clean_html_tags(None) == ""

def test_clean_html_tags_complex():
    text = "<div>Hello&nbsp;<b>World</b> &amp; others</div>"
    assert clean_html_tags(text) == "Hello World & others"
