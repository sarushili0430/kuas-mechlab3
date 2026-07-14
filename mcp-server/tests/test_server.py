from ml3_mcp.server import mcp


async def test_tools_registered():
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert {
        "drive",
        "stop",
        "capture_camera",
        "record_status",
        "record_start",
        "record_stop",
        "record_discard",
    } <= names
