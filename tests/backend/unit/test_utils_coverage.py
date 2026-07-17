import pytest

from backend.services.utils import clean_html_tags, geocode_location


@pytest.mark.asyncio
async def test_geocode_location_normalizes_surrounding_whitespace():
    coords = await geocode_location("  Basel  ")
    assert coords is not None
    assert coords.lat == 47.5596
    assert coords.lon == 7.5886


@pytest.mark.asyncio
async def test_geocode_location_does_not_guess_unknown_places():
    assert await geocode_location("NonExistentCity") is None


def test_clean_html_tags_empty():
    assert clean_html_tags("") == ""
    assert clean_html_tags(None) == ""


def test_clean_html_tags_complex():
    text = "<div>Hello&nbsp;<b>World</b> &amp; others</div>"
    assert clean_html_tags(text) == "Hello World & others"
