import logging
import httpx
from enum import Enum
from typing import Optional, Any, Dict
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class ExecutionMode(str, Enum):
    STEALTH = "stealth"
    FAST = "fast"

class ProxyPool:
    pass

class ScraperSession:
    def __init__(self, mode: ExecutionMode = ExecutionMode.FAST, proxy_pool: Optional[ProxyPool] = None, base_url: Optional[str] = None):
        self.mode = mode
        self.base_url = base_url
        self.client: Optional[httpx.AsyncClient] = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        }
        self.csrf_token: Optional[str] = None

    async def start(self):
        self.client = httpx.AsyncClient(headers=self.headers, verify=False, follow_redirects=True, timeout=30.0)

    async def close(self):
        if self.client:
            await self.client.aclose()

    async def get(self, url: str):
        if not self.client:
            await self.start()
        return await self.client.get(url)

    async def refresh_csrf_token(self, url: str):
        """Fetch index page to get CSRF token (Angular app)."""
        # JobRoom uses X-XSRF-TOKEN header from cookies or similar.
        # usually Angular sets a cookie 'XSRF-TOKEN', client reads it and sends 'X-XSRF-TOKEN'.
        response = await self.get(url)
        # In many systems, just visiting the page sets the cookie.
        # Httpx client stores cookies automatically.
        # We might need to extract it manually if the client logic expects it in a header.
        
        # Check cookies
        for cookie in self.client.cookies.jar:
            if cookie.name == "XSRF-TOKEN":
                self.csrf_token = cookie.value
                self.client.headers["X-XSRF-TOKEN"] = self.csrf_token
                logger.info("CSRF Token refreshed")
                break

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def with_retry_csrf(self, method: str, url: str, csrf_refresh_url: str, json: Optional[Dict] = None):
        if not self.client:
            await self.start()
        
        # Ensure we have CSRF if needed
        if method in ["POST", "PUT", "DELETE"] and not self.csrf_token:
            await self.refresh_csrf_token(csrf_refresh_url)
            
        try:
            response = await self.client.request(method, url, json=json)
            if response.status_code == 403 or response.status_code == 401:
                logger.warning("CSRF/Auth failed, retrying once...")
                await self.refresh_csrf_token(csrf_refresh_url)
                response = await self.client.request(method, url, json=json)
            
            response.raise_for_status()
            return response
        except httpx.HTTPError as e:
            logger.error(f"HTTP Request failed: {e}")
            raise

