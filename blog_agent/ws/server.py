import asyncio
import logging
from collections.abc import Awaitable
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from blog_agent.agent.blog_agent import BlogWorkflowService, EmitEvent
from blog_agent.models import (
    CancelRun,
    ClientMessage,
    ClientMessageType,
    EventEnvelope,
    EventType,
    Phase,
    RunStatus,
    SessionRuntime,
    SessionState,
    UserMessage,
)

logger = logging.getLogger(__name__)


class SessionManager:
    """Manage websocket sessions and bridge messages to the workflow service."""

    def __init__(self, workflow: BlogWorkflowService) -> None:
        self.workflow = workflow
        self.sessions: dict[str, SessionRuntime] = {}
        self.connections: dict[str, WebSocket] = {}

    def get_or_create_runtime(self, session_id: str) -> SessionRuntime:
        """Return the active runtime for a session, creating it if needed."""
        runtime = self.sessions.get(session_id)
        if runtime is None:
            runtime = SessionRuntime(SessionState(session_id=session_id))
            self.sessions[session_id] = runtime
        return runtime

    async def connect(self, session_id: str, websocket: WebSocket) -> SessionRuntime:
        """Accept a websocket and emit the initial session-ready event.

        Args:
            session_id: Stable session identifier from the websocket route.
            websocket: Accepted websocket connection.

        Returns:
            The session runtime associated with the connection.
        """
        await websocket.accept()
        self.connections[session_id] = websocket
        runtime = self.get_or_create_runtime(session_id)
        await self.emit(
            session_id,
            EventType.SESSION_READY,
            runtime.state.latest_run_id,
            runtime.state.phase,
            {
                "session_id": session_id,
                "phase": runtime.state.phase.value,
                "stage": runtime.state.stage.value,
            },
        )
        return runtime

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        """Remove the websocket connection if it matches the active socket."""
        if self.connections.get(session_id) is websocket:
            self.connections.pop(session_id, None)

    async def emit(
        self,
        session_id: str,
        event_type: EventType | str,
        run_id: str | None,
        phase: Phase | None,
        payload: dict[str, Any],
    ) -> None:
        """Send an event envelope to the connected client if available."""
        websocket = self.connections.get(session_id)
        if websocket is None:
            return
        envelope = EventEnvelope(
            type=event_type,
            session_id=session_id,
            run_id=run_id,
            phase=phase,
            data=payload,
        )
        await websocket.send_json(envelope.model_dump(mode="json"))

    async def handle_message(self, session_id: str, payload: dict[str, Any]) -> None:
        """Parse and dispatch a client payload for the given session."""
        runtime = self.get_or_create_runtime(session_id)
        try:
            message = self._parse_message(payload)
        except (ValidationError, ValueError) as exc:
            await self.emit(
                session_id,
                EventType.ERROR,
                runtime.state.latest_run_id,
                runtime.state.phase,
                {"message": str(exc)},
            )
            return

        if isinstance(message, CancelRun):
            await self._cancel_current_run(session_id, runtime)
            return

        if runtime.current_task and not runtime.current_task.done():
            await self.emit(
                session_id,
                EventType.ERROR,
                runtime.state.latest_run_id,
                runtime.state.phase,
                {"message": "A run is already in progress for this session."},
            )
            return

        if isinstance(message, UserMessage):
            runtime.current_task = asyncio.create_task(
                self._run_workflow_task(
                    session_id,
                    runtime,
                    self.workflow.handle_user_message(runtime, message.text, self._emit_for(session_id)),
                )
            )

    async def _run_workflow_task(
        self,
        session_id: str,
        runtime: SessionRuntime,
        coro: Awaitable[None],
    ) -> None:
        """Execute the workflow task and convert failures into events."""
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Workflow task failed")
            await self.emit(
                session_id,
                EventType.ERROR,
                runtime.state.latest_run_id,
                runtime.state.phase,
                {"message": str(exc)},
            )
            await self.emit(
                session_id,
                EventType.RUN_COMPLETE,
                runtime.state.latest_run_id,
                runtime.state.phase,
                {"status": RunStatus.FAILED.value},
            )
        finally:
            runtime.current_task = None

    def _emit_for(self, session_id: str) -> EmitEvent:
        """Build an event callback bound to the given session."""
        async def _emit(
            event_type: EventType | str,
            run_id: str | None,
            phase: Phase | None,
            payload: dict[str, Any],
        ) -> None:
            await self.emit(session_id, event_type, run_id, phase, payload)

        return _emit

    async def _cancel_current_run(self, session_id: str, runtime: SessionRuntime) -> None:
        """Cancel the active workflow task and emit completion."""
        task = runtime.current_task
        if task and not task.done():
            task.cancel()
            await self.emit(
                session_id,
                EventType.RUN_COMPLETE,
                runtime.state.latest_run_id,
                runtime.state.phase,
                {"status": RunStatus.CANCELLED.value},
            )

    def _parse_message(self, payload: dict[str, Any]) -> ClientMessage:
        """Parse an inbound websocket payload into a typed client message."""
        message_type = payload.get("type")
        if message_type == ClientMessageType.USER_MESSAGE.value:
            return UserMessage.model_validate(payload)
        if message_type == ClientMessageType.CANCEL_RUN.value:
            return CancelRun.model_validate(payload)
        raise ValueError(f"Unsupported message type: {message_type!r}")


def create_router(session_manager: SessionManager) -> APIRouter:
    """Create the websocket router for the blog-writing session flow."""
    router = APIRouter()

    @router.websocket("/ws/blog/{session_id}")
    async def blog_socket(websocket: WebSocket, session_id: str) -> None:
        """Handle the blog websocket lifecycle for a single session."""
        runtime = await session_manager.connect(session_id, websocket)
        try:
            while True:
                payload = await websocket.receive_json()
                await session_manager.handle_message(session_id, payload)
        except WebSocketDisconnect:
            session_manager.disconnect(session_id, websocket)
        except Exception as exc:  # pragma: no cover - defensive runtime path
            logger.exception("Unhandled websocket error")
            await session_manager.emit(
                session_id,
                EventType.ERROR,
                runtime.state.latest_run_id,
                runtime.state.phase,
                {"message": str(exc)},
            )
            session_manager.disconnect(session_id, websocket)

    return router
