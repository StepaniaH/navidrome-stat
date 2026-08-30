import hashlib
import os
import secrets
import string

import httpx
from dotenv import load_dotenv

DEFAULT_COVER_ART_MAX_BYTES = 10 * 1024 * 1024


class CoverArtTooLargeError(ValueError):
    """The upstream cover exceeded the bounded proxy response size."""


# Support local .env configuration.
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
            "v": "1.16.1", # Subsonic API version
            "c": "navidrome-statistic", # Client identifier
            "f": "json" # Request JSON responses
        }

    async def get_now_playing(self):
        return await self._get_json("getNowPlaying")

    async def get_playlist(self, playlist_id: str):
        """Return the full playlist envelope (smart-playlist backfill source)."""
        return await self._get_json("getPlaylist", id=playlist_id)

    async def get_song_history(self, *, size: int, offset: int):
        """Return one getSongHistory page (endpoint proposed upstream, PR #5650)."""
        return await self._get_json("getSongHistory", size=str(size), offset=str(offset))

    async def get_cover_art(
        self,
        item_id: str,
        size: int,
        *,
        max_bytes: int = DEFAULT_COVER_ART_MAX_BYTES,
    ):
        """Return raw cover art bytes and their content type."""
        params = self.get_auth_params()
        params.pop("f", None)
        params["id"] = item_id
        params["size"] = str(size)
        async with self._http_client.stream(
            "GET",
            f"{self.url}/rest/getCoverArt",
            params=params,
        ) as response:
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length is not None:
                try:
                    declared_bytes = int(content_length)
                except ValueError:
                    declared_bytes = None
                if declared_bytes is not None and declared_bytes > max_bytes:
                    raise CoverArtTooLargeError("cover art response is too large")
            data = bytearray()
            async for chunk in response.aiter_bytes():
                if len(data) + len(chunk) > max_bytes:
                    raise CoverArtTooLargeError("cover art response is too large")
                data.extend(chunk)
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
            return bytes(data), content_type

    async def search3(self, query: str, *, album_count: int = 5):
        """Return album hits for a free-text search."""
        data = await self._get_json(
            "search3",
            query=query,
            artistCount="0",
            albumCount=str(album_count),
            songCount="0",
        )
        envelope = data.get("subsonic-response", {}) if isinstance(data, dict) else {}
        result = envelope.get("searchResult3", {}) if isinstance(envelope, dict) else {}
        albums = result.get("album", []) if isinstance(result, dict) else []
        if isinstance(albums, dict):
            albums = [albums]
        return [album for album in albums if isinstance(album, dict)]

    async def get_open_subsonic_extensions(self):
        """Return advertised OpenSubsonic extensions, if the server supports it."""
        return await self._get_json("getOpenSubsonicExtensions")

    async def supports_playback_report(self) -> bool:
        """Return whether the server advertises the playbackReport extension."""
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

    async def supports_song_history(self) -> bool:
        """Probe the proposed OpenSubsonic getSongHistory endpoint."""
        try:
            data = await self._get_json("getSongHistory", size="1")
        except (httpx.HTTPError, ValueError, TypeError, RuntimeError):
            return False
        return self.response_is_ok(data)

    @staticmethod
    def response_is_ok(data) -> bool:
        return (
            isinstance(data, dict)
            and isinstance(data.get("subsonic-response"), dict)
            and data["subsonic-response"].get("status") == "ok"
        )

    @staticmethod
    def now_playing_entries(data) -> list:
        """Extract entries from an ok response; missing nowPlaying means idle."""
        envelope = data.get("subsonic-response") if isinstance(data, dict) else None
        now_playing = envelope.get("nowPlaying") if isinstance(envelope, dict) else None
        if not isinstance(now_playing, dict):
            return []
        entries = now_playing.get("entry")
        if entries is None:
            return []
        return entries

    async def _get_json(self, method: str, **extra):
        params = self.get_auth_params()
        params.update(extra)
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
