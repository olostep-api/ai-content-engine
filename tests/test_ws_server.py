from __future__ import annotations

import asyncio

from blog_agent.models import Phase
from blog_agent.ws.server import SessionManager


class FakeWorkflow:
    async def handle_user_message(self, runtime, text, emit):
        runtime.state.latest_run_id = "run-1"
        runtime.state.phase = Phase.OUTLINE
        await emit("assistant_message", "run-1", Phase.OUTLINE, {"message": "Outline ready."})
        await emit("artifact_ready", "run-1", Phase.OUTLINE, {"kind": "outline", "payload": {"title": "Outline", "sections": [], "sources": []}})
        await emit("run_complete", "run-1", Phase.OUTLINE, {"status": "awaiting_user"})


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def accept(self) -> None:
        return None

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)


def test_session_ready_and_user_message_events() -> None:
    asyncio.run(_test_session_ready_and_user_message_events())


async def _test_session_ready_and_user_message_events() -> None:
    manager = SessionManager(FakeWorkflow())
    websocket = FakeWebSocket()
    await manager.connect("session-1", websocket)
    await manager.handle_message("session-1", {"type": "user_message", "text": "write about AI"})
    await asyncio.sleep(0)

    assert websocket.messages[0]["type"] == "session_ready"
    assert [message["type"] for message in websocket.messages[1:4]] == [
        "assistant_message",
        "artifact_ready",
        "run_complete",
    ]


def test_rejects_concurrent_runs() -> None:
    asyncio.run(_test_rejects_concurrent_runs())


async def _test_rejects_concurrent_runs() -> None:
    manager = SessionManager(FakeWorkflow())
    runtime = manager.get_or_create_runtime("session-2")
    runtime.current_task = asyncio.create_task(asyncio.sleep(1))
    websocket = FakeWebSocket()
    await manager.connect("session-2", websocket)
    await manager.handle_message("session-2", {"type": "user_message", "text": "write about AI"})

    assert websocket.messages[-1]["type"] == "error"


def test_rejects_removed_outline_decision_messages() -> None:
    asyncio.run(_test_rejects_removed_outline_decision_messages())


async def _test_rejects_removed_outline_decision_messages() -> None:
    manager = SessionManager(FakeWorkflow())
    websocket = FakeWebSocket()
    await manager.connect("session-3", websocket)
    await manager.handle_message(
        "session-3",
        {"type": "outline_decision", "decision": "approve", "feedback": None},
    )

    assert websocket.messages[-1]["type"] == "error"
