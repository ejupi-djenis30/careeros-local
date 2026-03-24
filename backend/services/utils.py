import math
import re
import asyncio
import threading
import fitz  # PyMuPDF
from typing import Optional
from fastapi import UploadFile, HTTPException

_geocode_cache: dict = {}
_geocode_cache_lock = threading.Lock()

def clean_html_tags(text: str) -> str:
    """Remove HTML tags like <em>, &nbsp;, etc. from text."""
    if not text:
        return ""
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', '', text)
    # Decode HTML entities
    clean = clean.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    # Normalize whitespace
    return " ".join(clean.split())

async def extract_text_from_file(file: UploadFile) -> str:
    content_type = file.content_type
    filename = file.filename.lower()
    
    try:
        if filename.endswith(".pdf"):
            content = await file.read()
            return await asyncio.to_thread(_extract_from_pdf, content)
        elif filename.endswith(".txt") or filename.endswith(".md"):
            content = await file.read()
            return content.decode("utf-8")
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type. Please upload PDF, TXT, or MD.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process file: {str(e)}")

def _extract_from_pdf(content: bytes) -> str:
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        return text
    except Exception as e:
        raise Exception(f"PDF parsing error: {str(e)}")


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points on Earth in km."""
    R = 6371.0  # Earth radius in km
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def calculate_distance(coords1: tuple, coords2: tuple) -> float:
    """Wrapper for haversine_distance taking tuples (lat, lon)."""
    return haversine_distance(coords1[0], coords1[1], coords2[0], coords2[1])


async def geocode_location(city: str, client: Optional["httpx.AsyncClient"] = None) -> Optional["Coordinates"]:
    """
    Resolve a city name to Coordinates (lat, lon).
    Uses a local cache for major Swiss cities, an in-memory dynamic cache, and falls back to Nominatim API.
    Can accept a shared httpx.AsyncClient for connection pooling.
    """
    from backend.providers.jobs.models import Coordinates
    
    if not city:
        return None
    
    normalized = city.lower().strip()
    
    # 1. Local Cache for major Swiss cities (to avoid external API calls)
    SWISS_CITIES_COORDS = {
        "zurich": (47.3769, 8.5417),
        "zürich": (47.3769, 8.5417),
        "bern": (46.9480, 7.4474),
        "geneva": (46.2044, 6.1432),
        "genève": (46.2044, 6.1432),
        "genf": (46.2044, 6.1432),
        "basel": (47.5596, 7.5886),
        "lausanne": (46.5197, 6.6323),
        "lucerne": (47.0502, 8.3093),
        "luzern": (47.0502, 8.3093),
        "st. gallen": (47.4239, 9.3747),
        "sankt gallen": (47.4239, 9.3747),
        "lugano": (46.0037, 8.9511),
        "winterthur": (47.5000, 8.7167),
        "biel": (47.1367, 7.2467),
        "bienne": (47.1367, 7.2467),
        "thun": (46.7512, 7.6217),
        "koniz": (46.9242, 7.4202),
        "köniz": (46.9242, 7.4202),
        "fribourg": (46.8064, 7.1619),
        "freiburg": (46.8064, 7.1619),
        "schaffhausen": (47.6973, 8.6349),
        "chur": (46.8507, 9.5307),
        "neuchatel": (46.9899, 6.9290),
        "neuchâtel": (46.9899, 6.9290),
        "verniere": (46.2167, 6.0833),
        "uetikon": (47.2667, 8.6833),
        "dietikon": (47.4051, 8.4036),
        "dubendorf": (47.3969, 8.6153),
        "dübendorf": (47.3969, 8.6153),
    }
    
    if normalized in SWISS_CITIES_COORDS:
        lat, lon = SWISS_CITIES_COORDS[normalized]
        return Coordinates(lat=lat, lon=lon)
        
    global _geocode_cache
    with _geocode_cache_lock:
        if normalized in _geocode_cache:
            return _geocode_cache[normalized]
        
    # 2. Nominatim Fallback
    import httpx
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": f"{city}, Switzerland",
            "format": "json",
            "limit": 1
        }
        headers = {
            "User-Agent": "JobHunterAI/1.0 (contact: info@jobhunterai.ch)"
        }
        
        async def fetch(c):
            resp = await c.get(url, params=params, headers=headers, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                if data and len(data) > 0:
                    coords = Coordinates(
                        lat=float(data[0]["lat"]),
                        lon=float(data[0]["lon"])
                    )
                    with _geocode_cache_lock:
                        _geocode_cache[normalized] = coords
                    return coords
            return None

        if client:
            return await fetch(client)
        else:
            async with httpx.AsyncClient() as c:
                return await fetch(c)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Geocoding failed for {city}: {e}")
        
    return None
