import json

import httpx

from ml3_mcp import record


def _patch_client(monkeypatch, handler):
    real_client = httpx.AsyncClient  # capture before patching to avoid recursion

    def _factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(record.httpx, "AsyncClient", _factory)


async def test_start_builds_body(monkeypatch):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["json"] = json.loads(request.content) if request.content else None
        return httpx.Response(200, json={"recording": True, "index": 1})

    _patch_client(monkeypatch, handler)
    data = await record.start("http://x/record/start", route="r1", rear=True)

    assert seen["method"] == "POST"
    assert seen["url"].endswith("/record/start")
    assert seen["json"] == {"route": "r1", "rear": True}
    assert data["recording"] is True
    assert data["_http_status"] == 200


async def test_409_passthrough(monkeypatch):
    def handler(request):
        return httpx.Response(
            409, json={"recording": None, "error": "already_recording"}
        )

    _patch_client(monkeypatch, handler)
    data = await record.start("http://x/record/start")
    assert data["_http_status"] == 409
    assert data["error"] == "already_recording"


async def test_stop_and_discard(monkeypatch):
    calls: list = []

    def handler(request):
        calls.append((request.method, str(request.url)))
        return httpx.Response(200, json={"recording": False})

    _patch_client(monkeypatch, handler)
    await record.stop("http://x/record/stop", label="failure", notes="hit wall")
    await record.discard("http://x/record/discard")
    assert calls[0][1].endswith("/record/stop")
    assert calls[1][1].endswith("/record/discard")
