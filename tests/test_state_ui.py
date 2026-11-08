import asyncio
import json
import socket

from fastapi.testclient import TestClient
import httpx
import pytest

from server.rules import UNSPECIFIED
from server.service import RuleService
from server.state import SessionState
from server.ui.app import create_app
from server.ui.sse import encode_event


def test_search_sync_update_same_turn_and_preserve_user_selected_citation(service):
    q = "TR拿着五色石还能拿塔基吗？"
    r = service.search_rules(q)
    assert r["ui_started"] is True
    service.state.select(service.store.citation("4.4.2"))
    service.sync_answer(q, "不能。", r["citations"], r["turn_id"])
    snapshot = service.state.snapshot()
    assert len(snapshot["turns"]) == 1
    assert snapshot["turns"][0]["status"] == "answered"
    assert snapshot["selected"]["page"] == 20
    assert service.open_ui()["ui_started"] is False
    r2 = service.search_rules(q)
    assert r2["turn_id"] != r["turn_id"]
    assert len(service.state.turns) == 2


def test_no_basis_sync_clears_stale_highlight(service):
    service.get_clause("3.6.8")
    r = service.search_rules("今天食堂吃什么")
    synced = service.sync_answer(r["question"], "凭空编的答案", [], r["turn_id"])
    assert synced["answer"] == UNSPECIFIED
    assert service.state.selected is None


async def test_thread_safe_sse_order_replay_and_snapshot(store):
    state = SessionState()
    key, queue = state.subscribe()
    assert (await queue.get())["event"] == "snapshot"
    await asyncio.to_thread(state.question, "五色石？", store.citations(["3.6.8"]))
    events = [await asyncio.wait_for(queue.get(), 2) for _ in range(3)]
    assert [e["event"] for e in events] == ["question", "citations", "jump"]
    state.unsubscribe(key)
    key2, q2 = state.subscribe(last_id=1)
    assert [(await q2.get())["event"] for _ in range(2)] == ["citations", "jump"]
    state.unsubscribe(key2)
    key3, q3 = state.subscribe(last_id=999)
    assert (await q3.get())["data"]["selected"]["page"] == 17
    state.unsubscribe(key3)


def test_sse_serialization_is_single_json_data_line():
    encoded = encode_event({"id": 3, "event": "answer", "data": {"answer": "第一行\n第二行"}})
    lines = encoded.splitlines()
    assert lines[0] == "id: 3"
    assert json.loads(lines[2][6:])["answer"] == "第一行\n第二行"


def test_port_conflict_uses_different_loopback_port(store):
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0)); blocker.listen(1)
        occupied = blocker.getsockname()[1]
        s = RuleService(store, port=occupied)
        try:
            result = s.open_ui()
            assert s.ui.port != occupied
            assert s.ui.socket.getsockname()[0] == "127.0.0.1"
            assert httpx.get(result["ui_url"], timeout=3).status_code == 200
        finally:
            s.close()


def test_local_http_security_and_jump(service):
    with TestClient(create_app(service), base_url="http://127.0.0.1") as client:
        session = {"session": service.state.session_id}
        assert client.get("/api/state").status_code == 403
        assert client.get("/api/state", params={"session": "中文"}).status_code == 403
        assert client.get("/api/state", params=session, headers={"Origin": "https://evil.example"}).status_code == 403
        assert client.get("/api/state", params=session, headers={"Host": "evil.example"}).status_code == 400
        assert client.get("/static/%2e%2e/%2e%2e/data/clauses.json").status_code == 404
        assert client.post("/api/jump", params=session, content="clause_id=3.6.8", headers={"Content-Type": "application/x-www-form-urlencoded"}).status_code == 415
        assert client.post("/api/jump", params=session, json={"clause_id": "3.6.8"}).json()["citation"]["page"] == 17
        assert client.post("/api/jump", params=session, json={"clause_id": "99.9.9"}).status_code == 404
        assert client.post("/api/ask", params=session, json={"question": "五色石"}).status_code == 409
        assert client.post("/api/clear", params=session, json={}).json()["cleared"]
        assert service.state.selected is None
        pdf = client.get("/rules.pdf", params=session)
        assert pdf.content.startswith(b"%PDF")
        assert "no-store" in pdf.headers["cache-control"]


async def test_live_sse_connection_delivers_question_answer_and_jump(service):
    service.open_ui()
    url = f"http://127.0.0.1:{service.ui.port}/events"
    events = []
    async with httpx.AsyncClient(timeout=5) as client:
        async with client.stream("GET", url, params={"session": service.state.session_id}) as response:
            assert response.status_code == 200
            lines = response.aiter_lines()
            async for line in lines:
                if line.startswith("event: snapshot"):
                    break
            r = service.search_rules("TR拿着五色石还能拿塔基吗？")
            service.sync_answer(r["question"], "不能。", r["citations"], r["turn_id"])
            async for line in lines:
                if line.startswith("event: "):
                    events.append(line[7:])
                if events.count("citations") == 2:
                    break
    assert events == ["question", "citations", "jump", "answer", "citations"]
