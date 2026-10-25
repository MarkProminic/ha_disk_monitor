"""HTTP client for one disk-agent."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp


class DiskAgentError(Exception):
    """The agent could not be reached or refused the request."""


class DiskAgentAuthError(DiskAgentError):
    """The agent refused the credential."""


class DiskAgentClient:
    """Calls one disk-agent over HTTP or HTTPS.

    Takes the aiohttp session, the base URL and the API key; every method
    answers the decoded JSON body or raises DiskAgentError.
    """

    def __init__(self, session: aiohttp.ClientSession, base_url: str, api_key: str | None) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    @property
    def api_key(self) -> str | None:
        """The API key every authenticated call sends."""
        return self._api_key

    async def _request(self, method: str, path: str, json: dict | None = None, authenticated: bool = True) -> Any:
        headers = {}
        if authenticated and self._api_key:
            headers["X-API-Key"] = self._api_key
        try:
            async with asyncio.timeout(60):
                async with self._session.request(method, f"{self._base_url}{path}", json=json, headers=headers) as response:
                    if response.status in (401, 403):
                        raise DiskAgentAuthError(f"{response.status} from {path}")
                    if response.status >= 400:
                        text = await response.text()
                        raise DiskAgentError(f"{response.status} from {path}: {text[:200]}")
                    return await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise DiskAgentError(f"{method} {path}: {err}") from err

    async def status(self) -> dict:
        """GET /api/status, public."""
        return await self._request("GET", "/api/status", authenticated=False)

    async def bootstrap(self, setup_token: str, name: str) -> str:
        """POST /api/api-keys/bootstrap with the setup token; answers the minted key and keeps it."""
        body = await self._request(
            "POST",
            "/api/api-keys/bootstrap",
            json={"setup_token": setup_token, "name": name, "description": "Home Assistant Disk Monitor"},
            authenticated=False,
        )
        self._api_key = body["api_key"]
        return self._api_key

    async def report(self) -> dict:
        """GET /api/report."""
        return await self._request("GET", "/api/report")
