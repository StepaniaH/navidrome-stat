import hashlib
import os
import secrets
import string

import httpx
from dotenv import load_dotenv

# Load .env file for local development
load_dotenv()

def generate_auth(password: str):
    salt = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(6))
    token = hashlib.md5((password + salt).encode()).hexdigest()
    return token, salt

class NavidromeClient:
    def __init__(self, url: str = None, user: str = None, password: str = None):
        self.url = url or os.getenv("NAVIDROME_URL")
        self.user = user or os.getenv("NAVIDROME_USER")
        self.password = password or os.getenv("NAVIDROME_PASS")
        
        if not all([self.url, self.user, self.password]):
            raise ValueError("Missing Navidrome configuration. Provide via __init__ or environment variables (NAVIDROME_URL, NAVIDROME_USER, NAVIDROME_PASS).")
        
        # Strip trailing slash from URL
        self.url = self.url.rstrip("/")
        self._http_client = httpx.AsyncClient(
            trust_env=False,
            timeout=httpx.Timeout(10.0),
        )

    def get_auth_params(self):
        token, salt = generate_auth(self.password)
        return {
            "u": self.user,
            "t": token,
            "s": salt,
            "v": "1.16.1", # Subsonic version compatibility
            "c": "navidrome-statistic", # Client identifier
            "f": "json" # Force JSON response
        }

    async def get_now_playing(self):
        return await self._get_json("getNowPlaying")

    async def get_open_subsonic_extensions(self):
        """Return advertised OpenSubsonic extensions, if the server supports it."""
        return await self._get_json("getOpenSubsonicExtensions")

    async def supports_playback_report(self) -> bool:
        """Capability-detect the standardized now-playing progress fields.

        Unsupported endpoints and malformed extension payloads are treated as
        a legacy server so polling remains backwards compatible.
        """
        try:
            data = await self.get_open_subsonic_extensions()
        except (httpx.HTTPError, ValueError, TypeError):
            return False
        envelope = data.get("subsonic-response", {}) if isinstance(data, dict) else {}
        if envelope.get("status") != "ok":
            return False
        extensions = envelope.get("openSubsonicExtensions", {})
        if isinstance(extensions, dict):
            extensions = extensions.get("openSubsonicExtension", extensions.get("extension", []))
        if isinstance(extensions, dict):
            extensions = [extensions]
        if not isinstance(extensions, list):
            return False
        return any(
            isinstance(extension, dict)
            and str(extension.get("name", "")).lower() == "playbackreport"
            for extension in extensions
        )

    @staticmethod
    def response_is_ok(data) -> bool:
        return (
            isinstance(data, dict)
            and isinstance(data.get("subsonic-response"), dict)
            and data["subsonic-response"].get("status") == "ok"
        )

    async def _get_json(self, method: str):
        params = self.get_auth_params()
        endpoint = f"{self.url}/rest/{method}"
        response = await self._http_client.get(endpoint, params=params)
        response.raise_for_status()
        return response.json()
        
    async def close(self):
        await self._http_client.aclose()

if __name__ == "__main__":
    import asyncio
    async def main():
        client = None
        try:
            client = NavidromeClient()
            print("Fetching Now Playing data...")
            data = await client.get_now_playing()
            print("Request completed:", "ok" if client.response_is_ok(data) else "upstream_error")
        except Exception as exc:
            print(f"Request failed ({type(exc).__name__})")
        finally:
            if client is not None:
                await client.close()
    
    asyncio.run(main())
