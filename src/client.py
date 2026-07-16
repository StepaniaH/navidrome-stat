import hashlib
import secrets
import string
import os
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
        params = self.get_auth_params()
        endpoint = f"{self.url}/rest/getNowPlaying"
        response = await self._http_client.get(endpoint, params=params)
        response.raise_for_status()
        return response.json()
        
    async def close(self):
        await self._http_client.aclose()

if __name__ == "__main__":
    import asyncio
    async def main():
        try:
            client = NavidromeClient()
            print("Fetching Now Playing data...")
            data = await client.get_now_playing()
            import json
            print(json.dumps(data, indent=2))
        except Exception as e:
            print(f"Error: {e}")
    
    asyncio.run(main())
