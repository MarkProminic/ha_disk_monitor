"""HTTP client for one disk-agent."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import json
from typing import Any

import aiohttp


class DiskAgentError(Exception):
    """The agent could not be reached or refused the request."""


class DiskAgentAuthError(DiskAgentError):
    """The agent refused the API key."""


class DiskAgentClient:
    """Calls one disk-agent over HTTP or HTTPS.

    Takes the aiohttp session, the base URL and the API key; every method
    answers the decoded JSON body or raises DiskAgentError.
    """

    def __init__(self, session: aiohttp.ClientSession, base_url: str, api_key: str) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def _headers(self, authenticated: bool) -> dict[str, str]:
        return {"X-API-Key": self._api_key} if authenticated else {}

    @staticmethod
    def _check(response: aiohttp.ClientResponse, path: str) -> None:
        if response.status in (401, 403):
            raise DiskAgentAuthError(f"{response.status} from {path}")
        if response.status >= 400:
            raise DiskAgentError(f"{response.status} from {path}")

    async def _request(self, path: str, authenticated: bool = True) -> Any:
        try:
            async with asyncio.timeout(60):
                async with self._session.get(f"{self._base_url}{path}", headers=self._headers(authenticated)) as response:
                    self._check(response, path)
                    return await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise DiskAgentError(f"GET {path}: {err}") from err

    async def status(self) -> dict:
        """GET /api/status, public."""
        return await self._request("/api/status", authenticated=False)

    async def report(self) -> dict:
        """GET /api/report."""
        return await self._request("/api/report")

    async def events(self) -> AsyncIterator[dict]:
        """GET /api/events: yields each report the agent streams until the connection drops."""
        path = "/api/events"
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=None)
        try:
            async with self._session.get(f"{self._base_url}{path}", headers=self._headers(True), timeout=timeout) as response:
                self._check(response, path)
                data_lines: list[str] = []
                async for raw in response.content:
                    line = raw.decode("utf-8", "replace").rstrip("\r\n")
                    if line == "":
                        if data_lines:
                            yield json.loads("\n".join(data_lines))
                            data_lines = []
                        continue
                    if line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as err:
            raise DiskAgentError(f"GET {path}: {err}") from err
