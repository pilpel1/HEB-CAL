"""לחיצת יד אמיתית מול לקוח ה-SDK הרשמי, על שרת HTTP זמני."""
from __future__ import annotations

import asyncio
import threading

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from werkzeug.serving import make_server

from mcp_support import add_user, make_key


@pytest.fixture(scope="module")
def mcp_server(app):
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/mcp"
    finally:
        server.shutdown()


def test_official_client_handshakes_in_both_eras(app, mcp_server):
    user = add_user(app)
    token = make_key(app, user, "write")

    async def exercise(mode, expected_version):
        async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as http:
            transport = streamable_http_client(mcp_server, http_client=http)
            async with Client(transport, mode=mode) as client:
                assert client.protocol_version == expected_version
                listed = await client.list_tools()
                names = {tool.name for tool in listed.tools}
                assert {"list_events", "create_event", "update_event", "delete_event", "convert_date"} <= names
                created = await client.call_tool("create_event", {"title": f"sdk-{mode}", "date": "2026-12-01"})
                assert created.is_error is False
                event_id = created.structured_content["event"]["id"]
                listed_events = await client.call_tool("list_events", {"from": "2026-12-01", "to": "2026-12-01"})
                assert listed_events.is_error is False
                assert any(row["id"] == event_id for row in listed_events.structured_content["events"])
                deleted = await client.call_tool("delete_event", {"event_id": event_id})
                assert deleted.is_error is False
                assert deleted.structured_content["deleted"] is True

    asyncio.run(exercise("legacy", "2025-11-25"))
    asyncio.run(exercise("2026-07-28", "2026-07-28"))
