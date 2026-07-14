"""Thin async HTTP client for the robot's recording server (port 9002).

Wraps GET /record/status and POST /record/{start,stop,discard}. The server
returns JSON and uses HTTP 409 for state errors (already/not recording); we pass
the body through and stash the status code under ``_http_status`` so the agent
can see it."""
from __future__ import annotations

import httpx


async def _request(
    method: str, url: str, *, body: dict | None = None, timeout: float = 10.0
) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.request(method, url, json=body)
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text}
    if isinstance(data, dict):
        data.setdefault("_http_status", resp.status_code)
        return data
    return {"result": data, "_http_status": resp.status_code}


async def status(url: str) -> dict:
    return await _request("GET", url)


async def start(
    url: str,
    *,
    route: str | None = None,
    operator: str | None = None,
    rear: bool | None = None,
    state: bool | None = None,
) -> dict:
    body: dict = {}
    if route is not None:
        body["route"] = route
    if operator is not None:
        body["operator"] = operator
    if rear is not None:
        body["rear"] = rear
    if state is not None:
        body["state"] = state
    return await _request("POST", url, body=body or None)


async def stop(
    url: str, *, label: str | None = None, notes: str | None = None
) -> dict:
    body: dict = {}
    if label is not None:
        body["label"] = label
    if notes is not None:
        body["notes"] = notes
    return await _request("POST", url, body=body or None)


async def discard(url: str) -> dict:
    return await _request("POST", url)
