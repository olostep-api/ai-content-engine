import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from blog_agent.agent.prompts import (
    MANAGER_SYSTEM_PROMPT,
    WRITER_SYSTEM_PROMPT,
    build_draft_review_prompt,
    build_final_draft_message_prompt,
    build_manager_decision_prompt,
    build_manager_failure_prompt,
    build_outline_review_prompt,
    build_writer_draft_prompt,
    build_writer_draft_revision_prompt,
    build_writer_outline_prompt,
    build_writer_outline_revision_prompt,
)
from blog_agent.models import (
    ArtifactKind,
    ArtifactReview,
    AssistantReply,
    BlogBrief,
    DraftPayload,
    EventType,
    ReplyKind,
    RunStatus,
    ManagerDecision,
    OutlinePayload,
    OutlineSection,
    Phase,
    ResearchSource,
    SessionRuntime,
    SessionState,
    TranscriptMessage,
    WorkflowAction,
    WorkflowStage,
)
from blog_agent.agent.source_registry import SourceRegistry
from blog_agent.tools.tools import ToolProvider

logger = logging.getLogger(__name__)

try:  # pragma: no cover - dependency presence varies locally
    from agents import Agent, Runner, function_tool
except ImportError:  # pragma: no cover - dependency presence varies locally
    Agent = None
    Runner = None
    function_tool = None


EmitEvent = Callable[[EventType | str, str | None, Phase | None, dict[str, Any]], Awaitable[None]]
ArtifactT = TypeVar("ArtifactT", OutlinePayload, DraftPayload)
ModelT = TypeVar("ModelT", bound=BaseModel)

RUN_STATUS_AWAITING_USER = RunStatus.AWAITING_USER
RUN_STATUS_FAILED = RunStatus.FAILED
REPLY_KIND_INFO = ReplyKind.INFO
REPLY_KIND_ERROR = ReplyKind.ERROR
DRAFT_CHUNK_SIZE = 500


class OutlineResult(BaseModel):
    """Structured outline output produced by the writer agent."""

    title: str
    sections: list[OutlineSection] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class DraftResult(BaseModel):
    """Structured draft output produced by the writer agent."""

    markdown: str

    model_config = {"extra": "forbid"}


class BlogWorkflowService:
    """Orchestrate blog creation, review, and revision for one session."""

    max_outline_review_revisions = 1
    max_draft_review_revisions = 1

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self._validate_sdk()

    def _validate_sdk(self) -> None:
        if Agent is None or Runner is None or function_tool is None:
            raise RuntimeError(
                "openai-agents is not installed. Add `openai-agents` to your environment before running the server."
            )

    async def handle_user_message(
        self,
        runtime: SessionRuntime,
        text: str,
        emit: EmitEvent,
        *,
        allow_restart: bool = True,
    ) -> None:
        """Process a user message and route it through the workflow.

        Args:
            runtime: Session state container for the current websocket session.
            text: Raw user message text.
            emit: Callback used to send workflow events to the client.
            allow_restart: Whether a `start_new_blog` decision may reset state.
        """
        run_id = self._start_run(runtime, text)
        await self._emit_internal_message(
            emit,
            run_id,
            self._manager_progress_message(runtime.state.stage),
            phase=runtime.state.phase,
        )
        decision = await self._run_manager_decision(runtime, text)

        if decision.action == WorkflowAction.START_NEW_BLOG:
            await self._handle_start_new_blog(runtime, text, emit, run_id, decision, allow_restart=allow_restart)
            return

        self._apply_manager_decision(runtime.state, text, decision)
        await self._dispatch_manager_action(runtime, text, emit, run_id, decision)

    def _start_run(self, runtime: SessionRuntime, text: str) -> str:
        run_id = str(uuid.uuid4())
        runtime.state.last_user_message = text
        runtime.state.latest_run_id = run_id
        return run_id

    def _apply_manager_decision(self, state: SessionState, text: str, decision: ManagerDecision) -> None:
        self._append_transcript(state, "user", text)
        state.brief = decision.brief

    def _manager_progress_message(self, stage: WorkflowStage) -> str:
        if stage == WorkflowStage.AWAITING_OUTLINE_FEEDBACK:
            return "Reviewing your outline feedback..."
        if stage == WorkflowStage.AWAITING_DRAFT_FEEDBACK:
            return "Reviewing your draft feedback..."
        return "Reviewing your request..."

    async def _dispatch_manager_action(
        self,
        runtime: SessionRuntime,
        text: str,
        emit: EmitEvent,
        run_id: str,
        decision: ManagerDecision,
    ) -> None:
        match decision.action:
            case WorkflowAction.ASK_CLARIFICATION:
                await self._handle_clarification(runtime, emit, run_id, decision)
            case WorkflowAction.REPLY_WITH_ERROR:
                await self._handle_reply_with_error(runtime, emit, run_id, decision)
            case WorkflowAction.CREATE_OUTLINE:
                await self._emit_decision_preface(runtime, emit, run_id, decision, Phase.OUTLINE)
                await self._handle_create_outline(runtime, emit, run_id)
            case WorkflowAction.REVISE_OUTLINE:
                await self._emit_decision_preface(runtime, emit, run_id, decision, Phase.OUTLINE)
                await self._handle_revise_outline(runtime, text, emit, run_id, decision)
            case WorkflowAction.APPROVE_OUTLINE_AND_WRITE_DRAFT:
                await self._emit_decision_preface(runtime, emit, run_id, decision, Phase.DRAFT)
                await self._handle_approve_outline_and_write_draft(runtime, emit, run_id)
            case WorkflowAction.REVISE_DRAFT:
                await self._emit_decision_preface(runtime, emit, run_id, decision, Phase.DRAFT)
                await self._handle_revise_draft(runtime, text, emit, run_id, decision)
            case _:
                await self._handle_unsupported_action(runtime, emit, run_id, decision.action.value)

    async def _handle_start_new_blog(
        self,
        runtime: SessionRuntime,
        text: str,
        emit: EmitEvent,
        run_id: str,
        decision: ManagerDecision,
        *,
        allow_restart: bool,
    ) -> None:
        if allow_restart:
            self._reset_active_workflow(runtime)
            await self.handle_user_message(runtime, text, emit, allow_restart=False)
            return

        await self._emit_manager_reply(
            runtime,
            emit,
            run_id,
            decision.assistant_message or "Please send the new blog request again.",
            reply_kind=decision.reply_kind,
            phase=Phase.BRIEF,
        )
        await self._emit_awaiting_user_run(emit, run_id, Phase.BRIEF)

    async def _handle_clarification(
        self,
        runtime: SessionRuntime,
        emit: EmitEvent,
        run_id: str,
        decision: ManagerDecision,
    ) -> None:
        runtime.state.phase = Phase.BRIEF
        runtime.state.stage = WorkflowStage.COLLECTING_BRIEF
        await self._emit_manager_reply(
            runtime,
            emit,
            run_id,
            decision.assistant_message,
            reply_kind=decision.reply_kind,
            phase=Phase.BRIEF,
        )
        await self._emit_awaiting_user_run(emit, run_id, Phase.BRIEF)

    async def _handle_reply_with_error(
        self,
        runtime: SessionRuntime,
        emit: EmitEvent,
        run_id: str,
        decision: ManagerDecision,
    ) -> None:
        await self._emit_manager_reply(
            runtime,
            emit,
            run_id,
            decision.assistant_message,
            reply_kind=decision.reply_kind,
            phase=runtime.state.phase,
        )
        if decision.reply_kind == REPLY_KIND_ERROR:
            await self._emit_failed_run(emit, run_id, runtime.state.phase)
            return
        await self._emit_awaiting_user_run(emit, run_id, runtime.state.phase)

    async def _handle_create_outline(
        self,
        runtime: SessionRuntime,
        emit: EmitEvent,
        run_id: str,
    ) -> None:
        await self._create_or_revise_outline(runtime, emit, run_id)

    async def _handle_revise_outline(
        self,
        runtime: SessionRuntime,
        text: str,
        emit: EmitEvent,
        run_id: str,
        decision: ManagerDecision,
    ) -> None:
        if runtime.state.outline is None:
            await self._emit_missing_outline_for_revision(emit, run_id)
            return
        await self._create_or_revise_outline(
            runtime,
            emit,
            run_id,
            revision_instructions=decision.revision_instructions or text,
        )

    async def _handle_approve_outline_and_write_draft(
        self,
        runtime: SessionRuntime,
        emit: EmitEvent,
        run_id: str,
    ) -> None:
        if runtime.state.outline is None:
            await self._emit_missing_outline_for_draft(emit, run_id)
            return
        await self._create_or_revise_draft(runtime, emit, run_id)

    async def _handle_revise_draft(
        self,
        runtime: SessionRuntime,
        text: str,
        emit: EmitEvent,
        run_id: str,
        decision: ManagerDecision,
    ) -> None:
        if runtime.state.outline is None or runtime.state.latest_draft is None:
            await self._emit_missing_draft_for_revision(emit, run_id)
            return
        await self._create_or_revise_draft(
            runtime,
            emit,
            run_id,
            revision_instructions=decision.revision_instructions or text,
        )

    async def _handle_unsupported_action(
        self,
        runtime: SessionRuntime,
        emit: EmitEvent,
        run_id: str,
        action: str,
    ) -> None:
        await self._emit_error_and_fail(emit, run_id, runtime.state.phase, f"Unsupported workflow action: {action}")

    async def _emit_decision_preface(
        self,
        runtime: SessionRuntime,
        emit: EmitEvent,
        run_id: str,
        decision: ManagerDecision,
        phase: Phase,
    ) -> None:
        if decision.assistant_message.strip():
            await self._emit_manager_reply(
                runtime,
                emit,
                run_id,
                decision.assistant_message,
                reply_kind=REPLY_KIND_INFO,
                phase=phase,
            )

    async def _create_or_revise_outline(
        self,
        runtime: SessionRuntime,
        emit: EmitEvent,
        run_id: str,
        revision_instructions: str | None = None,
    ) -> None:
        state = runtime.state
        state.phase = Phase.OUTLINE

        await self._emit_internal_message(
            emit,
            run_id,
            "Revising the outline..." if revision_instructions else "Creating the outline...",
            phase=Phase.OUTLINE,
        )

        outline = await self._run_outline_writer(
            brief=state.brief,
            sources=state.sources,
            emit=emit,
            run_id=run_id,
            revision_instructions=revision_instructions,
            current_outline=state.outline,
        )
        state.sources = outline.sources
        if not await self._ensure_required_sources(
            runtime,
            emit,
            run_id,
            "No supporting sources were gathered for the outline.",
        ):
            return

        async def review_outline(candidate: OutlinePayload, revision_count: int) -> ArtifactReview:
            await self._emit_internal_message(emit, run_id, "Reviewing the outline...", phase=Phase.OUTLINE)
            return await self._review_outline_with_manager(
                state.brief,
                candidate,
                state.transcript,
                revision_number=revision_count,
            )

        async def revise_outline(candidate: OutlinePayload, instructions: str) -> OutlinePayload | None:
            await self._emit_internal_message(emit, run_id, "Revising the outline...", phase=Phase.OUTLINE)
            revised_outline = await self._run_outline_writer(
                brief=state.brief,
                sources=state.sources,
                emit=emit,
                run_id=run_id,
                revision_instructions=instructions,
                current_outline=candidate,
            )
            state.sources = revised_outline.sources
            if not await self._ensure_required_sources(
                runtime,
                emit,
                run_id,
                "The revised outline still has no supporting sources.",
            ):
                return None
            return revised_outline

        review_result = await self._run_review_cycle(
            outline,
            max_revisions=self.max_outline_review_revisions,
            review=review_outline,
            revise=revise_outline,
        )
        if review_result is None:
            return

        outline, review = review_result
        if review.action == "revise":
            await self._emit_outline_ready(
                runtime,
                emit,
                run_id,
                outline,
                "I revised the outline and this is the strongest version from the current pass. Reply with approval or tell me what to change.",
            )
            return

        if review.action != "approve":
            await self._emit_failed_run(emit, run_id, Phase.OUTLINE)
            return

        await self._emit_outline_ready(
            runtime,
            emit,
            run_id,
            outline,
            review.assistant_message or "I have an outline ready. Reply with approval or tell me what to change.",
        )

    async def _create_or_revise_draft(
        self,
        runtime: SessionRuntime,
        emit: EmitEvent,
        run_id: str,
        revision_instructions: str | None = None,
    ) -> None:
        state = runtime.state
        outline = state.outline
        if outline is None:
            raise RuntimeError("Draft generation requires an outline.")

        state.phase = Phase.DRAFT
        state.stage = WorkflowStage.DRAFTING

        await self._emit_internal_message(
            emit,
            run_id,
            "Revising the draft..." if revision_instructions else "Writing the draft...",
            phase=Phase.DRAFT,
        )

        draft = await self._run_draft_writer(
            brief=state.brief,
            outline=outline,
            draft=state.latest_draft,
            sources=state.sources,
            emit=emit,
            run_id=run_id,
            revision_instructions=revision_instructions,
        )
        state.sources = draft.sources
        if not await self._ensure_required_sources(
            runtime,
            emit,
            run_id,
            "No supporting sources were gathered for the draft.",
        ):
            return

        async def review_draft(candidate: DraftPayload, revision_count: int) -> ArtifactReview:
            await self._emit_internal_message(emit, run_id, "Reviewing the draft...", phase=Phase.DRAFT)
            return await self._review_draft_with_manager(
                state.brief,
                outline,
                candidate,
                state.transcript,
                revision_number=revision_count,
            )

        async def revise_draft(candidate: DraftPayload, instructions: str) -> DraftPayload | None:
            await self._emit_internal_message(emit, run_id, "Revising the draft...", phase=Phase.DRAFT)
            revised_draft = await self._run_draft_writer(
                brief=state.brief,
                outline=outline,
                draft=candidate,
                sources=state.sources,
                emit=emit,
                run_id=run_id,
                revision_instructions=instructions,
            )
            state.sources = revised_draft.sources
            if not await self._ensure_required_sources(
                runtime,
                emit,
                run_id,
                "The revised draft still has no supporting sources.",
            ):
                return None
            return revised_draft

        review_result = await self._run_review_cycle(
            draft,
            max_revisions=self.max_draft_review_revisions,
            review=review_draft,
            revise=revise_draft,
        )
        if review_result is None:
            return

        draft, review = review_result
        if review.action == "revise":
            final_message = await self._compose_final_draft_message(
                runtime,
                draft,
            )
            await self._emit_draft_ready(runtime, emit, run_id, draft, final_message)
            return

        if review.action != "approve":
            await self._emit_failed_run(emit, run_id, Phase.DRAFT)
            return

        await self._emit_draft_ready(
            runtime,
            emit,
            run_id,
            draft,
            review.assistant_message or "I have a draft ready. Tell me what to revise or ask for a new blog.",
        )

    async def _run_review_cycle(
        self,
        artifact: ArtifactT,
        *,
        max_revisions: int,
        review: Callable[[ArtifactT, int], Awaitable[ArtifactReview]],
        revise: Callable[[ArtifactT, str], Awaitable[ArtifactT | None]],
    ) -> tuple[ArtifactT, ArtifactReview] | None:
        revision_attempts = 0
        review_result = await review(artifact, revision_attempts)
        while review_result.action == "revise" and review_result.revision_instructions and revision_attempts < max_revisions:
            revision_attempts += 1
            revised_artifact = await revise(artifact, review_result.revision_instructions)
            if revised_artifact is None:
                return None
            artifact = revised_artifact
            review_result = await review(artifact, revision_attempts)
        return artifact, review_result

    async def _run_manager_decision(self, runtime: SessionRuntime, text: str) -> ManagerDecision:
        state = runtime.state
        agent = Agent(
            name="blog_manager",
            model=self.model,
            instructions=MANAGER_SYSTEM_PROMPT,
            output_type=ManagerDecision,
        )
        runner_result = await Runner.run(
            agent,
            input=build_manager_decision_prompt(
                stage=state.stage,
                user_message=text,
                brief=state.brief,
                outline=state.outline,
                draft=state.latest_draft,
                sources=state.sources,
                transcript=state.transcript,
            ),
        )
        return self._coerce_output(runner_result, ManagerDecision)

    async def _review_outline_with_manager(
        self,
        brief: BlogBrief,
        outline: OutlinePayload,
        transcript: list[TranscriptMessage],
        *,
        revision_number: int,
    ) -> ArtifactReview:
        agent = Agent(
            name="blog_manager_outline_review",
            model=self.model,
            instructions=MANAGER_SYSTEM_PROMPT,
            output_type=ArtifactReview,
        )
        runner_result = await Runner.run(
            agent,
            input=build_outline_review_prompt(
                brief=brief,
                outline=outline,
                transcript=transcript,
                revision_number=revision_number,
            ),
        )
        return self._coerce_output(runner_result, ArtifactReview)

    async def _review_draft_with_manager(
        self,
        brief: BlogBrief,
        outline: OutlinePayload,
        draft: DraftPayload,
        transcript: list[TranscriptMessage],
        *,
        revision_number: int,
    ) -> ArtifactReview:
        agent = Agent(
            name="blog_manager_draft_review",
            model=self.model,
            instructions=MANAGER_SYSTEM_PROMPT,
            output_type=ArtifactReview,
        )
        runner_result = await Runner.run(
            agent,
            input=build_draft_review_prompt(
                brief=brief,
                outline=outline,
                draft=draft,
                transcript=transcript,
                revision_number=revision_number,
            ),
        )
        return self._coerce_output(runner_result, ArtifactReview)

    async def _compose_failure_message(self, runtime: SessionRuntime, error_message: str) -> str:
        state = runtime.state
        agent = Agent(
            name="blog_manager_failure_reply",
            model=self.model,
            instructions=MANAGER_SYSTEM_PROMPT,
            output_type=AssistantReply,
        )
        runner_result = await Runner.run(
            agent,
            input=build_manager_failure_prompt(
                stage=state.stage,
                brief=state.brief,
                error_message=error_message,
            ),
        )
        return self._coerce_output(runner_result, AssistantReply).assistant_message

    async def _compose_final_draft_message(self, runtime: SessionRuntime, draft: DraftPayload) -> str:
        state = runtime.state
        outline = state.outline
        if outline is None:
            raise RuntimeError("Final draft messaging requires an outline.")

        agent = Agent(
            name="blog_manager_final_draft_reply",
            model=self.model,
            instructions=MANAGER_SYSTEM_PROMPT,
            output_type=AssistantReply,
        )
        runner_result = await Runner.run(
            agent,
            input=build_final_draft_message_prompt(
                brief=state.brief,
                outline=outline,
                draft=draft,
                transcript=state.transcript,
            ),
        )
        return self._coerce_output(runner_result, AssistantReply).assistant_message

    async def _run_outline_writer(
        self,
        *,
        brief: BlogBrief,
        sources: list[ResearchSource],
        emit: EmitEvent,
        run_id: str,
        revision_instructions: str | None,
        current_outline: OutlinePayload | None,
    ) -> OutlinePayload:
        tools, registry = self._build_writer_tools(
            seed_sources=sources,
            emit=emit,
            run_id=run_id,
            phase=Phase.OUTLINE,
        )
        agent = Agent(
            name="blog_writer_outline",
            model=self.model,
            instructions=WRITER_SYSTEM_PROMPT,
            tools=tools,
            output_type=OutlineResult,
        )
        prompt = (
            build_writer_outline_revision_prompt(
                brief=brief,
                outline=current_outline or OutlinePayload(title="", sections=[], sources=sources),
                revision_instructions=revision_instructions,
                sources=sources,
            )
            if revision_instructions and current_outline is not None
            else build_writer_outline_prompt(brief)
        )
        stream_result = Runner.run_streamed(agent, input=prompt)
        async for _ in stream_result.stream_events():
            pass
        final_output = stream_result.final_output_as(OutlineResult)
        return OutlinePayload(
            title=final_output.title,
            sections=final_output.sections,
            sources=registry.current_sources(),
        )

    async def _run_draft_writer(
        self,
        *,
        brief: BlogBrief,
        outline: OutlinePayload,
        draft: DraftPayload | None,
        sources: list[ResearchSource],
        emit: EmitEvent,
        run_id: str,
        revision_instructions: str | None,
    ) -> DraftPayload:
        tools, registry = self._build_writer_tools(
            seed_sources=sources,
            emit=emit,
            run_id=run_id,
            phase=Phase.DRAFT,
        )
        agent = Agent(
            name="blog_writer_draft",
            model=self.model,
            instructions=WRITER_SYSTEM_PROMPT,
            tools=tools,
            output_type=DraftResult,
        )
        prompt = (
            build_writer_draft_revision_prompt(
                brief=brief,
                outline=outline,
                draft=draft or DraftPayload(markdown="", sources=sources),
                revision_instructions=revision_instructions,
                sources=sources,
            )
            if revision_instructions and draft is not None
            else build_writer_draft_prompt(brief=brief, outline=outline, sources=sources)
        )
        stream_result = Runner.run_streamed(agent, input=prompt)
        async for _ in stream_result.stream_events():
            pass
        final_output = stream_result.final_output_as(DraftResult)
        return DraftPayload(markdown=final_output.markdown, sources=registry.current_sources())

    def _build_writer_tools(
        self,
        *,
        seed_sources: list[ResearchSource],
        emit: EmitEvent,
        run_id: str,
        phase: Phase,
    ) -> tuple[list[Any], SourceRegistry]:
        provider = ToolProvider(on_event=lambda event_type, payload: emit(event_type, run_id, phase, payload))
        registry = SourceRegistry.from_sources(seed_sources)

        @function_tool
        async def search_web(query: str, top_k: int = 5) -> dict[str, Any]:
            search_result = await provider.search_web(query, top_k)
            if search_result.get("error"):
                return search_result

            registry.record_search_results(search_result.get("results", []))
            return search_result

        @function_tool
        async def scrape_page(url: str) -> dict[str, str | None]:
            scrape_result = await provider.scrape_page(url)
            if scrape_result.get("error"):
                return scrape_result

            registry.record_scrape_result(url, scrape_result)
            return scrape_result

        return [search_web, scrape_page], registry

    async def _ensure_required_sources(
        self,
        runtime: SessionRuntime,
        emit: EmitEvent,
        run_id: str,
        error_message: str,
    ) -> bool:
        if runtime.state.brief.must_use_sources and not runtime.state.sources:
            await self._emit_writer_failure(runtime, emit, run_id, error_message)
            return False
        return True

    async def _emit_outline_ready(
        self,
        runtime: SessionRuntime,
        emit: EmitEvent,
        run_id: str,
        outline: OutlinePayload,
        assistant_message: str,
    ) -> None:
        runtime.state.outline = outline
        runtime.state.phase = Phase.OUTLINE
        runtime.state.stage = WorkflowStage.AWAITING_OUTLINE_FEEDBACK

        await self._emit_manager_reply(
            runtime,
            emit,
            run_id,
            assistant_message,
            reply_kind=REPLY_KIND_INFO,
            phase=Phase.OUTLINE,
        )
        await emit(
            EventType.ARTIFACT_READY,
            run_id,
            Phase.OUTLINE,
            {"kind": ArtifactKind.OUTLINE.value, "payload": outline.model_dump()},
        )
        await self._emit_awaiting_user_run(emit, run_id, Phase.OUTLINE)

    async def _emit_draft_ready(
        self,
        runtime: SessionRuntime,
        emit: EmitEvent,
        run_id: str,
        draft: DraftPayload,
        assistant_message: str,
    ) -> None:
        runtime.state.phase = Phase.DRAFT
        runtime.state.stage = WorkflowStage.AWAITING_DRAFT_FEEDBACK
        runtime.state.latest_draft = draft

        await self._emit_manager_reply(
            runtime,
            emit,
            run_id,
            assistant_message,
            reply_kind=REPLY_KIND_INFO,
            phase=Phase.DRAFT,
        )
        for chunk in self._chunk_markdown(draft.markdown, chunk_size=DRAFT_CHUNK_SIZE):
            await emit(
                EventType.ARTIFACT_DELTA,
                run_id,
                Phase.DRAFT,
                {"kind": ArtifactKind.DRAFT.value, "delta": chunk},
            )
        await emit(
            EventType.ARTIFACT_READY,
            run_id,
            Phase.DRAFT,
            {"kind": ArtifactKind.DRAFT.value, "payload": draft.model_dump()},
        )
        await self._emit_awaiting_user_run(emit, run_id, Phase.DRAFT)

    async def _emit_missing_outline_for_revision(self, emit: EmitEvent, run_id: str) -> None:
        await self._emit_error_and_fail(emit, run_id, Phase.OUTLINE, "No outline is available to revise.")

    async def _emit_missing_outline_for_draft(self, emit: EmitEvent, run_id: str) -> None:
        await self._emit_error_and_fail(emit, run_id, Phase.DRAFT, "No outline is available to draft from.")

    async def _emit_missing_draft_for_revision(self, emit: EmitEvent, run_id: str) -> None:
        await self._emit_error_and_fail(emit, run_id, Phase.DRAFT, "No draft is available to revise.")

    async def _emit_error_and_fail(
        self,
        emit: EmitEvent,
        run_id: str,
        phase: Phase | None,
        message: str,
    ) -> None:
        await emit(EventType.ERROR, run_id, phase, {"message": message})
        await self._emit_failed_run(emit, run_id, phase)

    async def _emit_writer_failure(
        self,
        runtime: SessionRuntime,
        emit: EmitEvent,
        run_id: str,
        error_message: str,
    ) -> None:
        assistant_message = await self._compose_failure_message(runtime, error_message)
        await self._emit_manager_reply(
            runtime,
            emit,
            run_id,
            assistant_message,
            reply_kind=REPLY_KIND_INFO,
            phase=runtime.state.phase,
        )
        await self._emit_failed_run(emit, run_id, runtime.state.phase)

    async def _emit_manager_reply(
        self,
        runtime: SessionRuntime,
        emit: EmitEvent,
        run_id: str,
        message: str,
        *,
        reply_kind: ReplyKind,
        phase: Phase | None,
    ) -> None:
        if not message.strip():
            return

        self._append_transcript(runtime.state, "assistant", message)
        event_type = EventType.ERROR if reply_kind == REPLY_KIND_ERROR else EventType.ASSISTANT_MESSAGE
        await emit(event_type, run_id, phase, {"message": message})

    async def _emit_internal_message(
        self,
        emit: EmitEvent,
        run_id: str,
        message: str,
        *,
        phase: Phase | None,
    ) -> None:
        if not message.strip():
            return

        await emit(EventType.INTERNAL_MESSAGE, run_id, phase, {"message": message})

    async def _emit_failed_run(self, emit: EmitEvent, run_id: str, phase: Phase | None) -> None:
        await self._emit_run_complete(emit, run_id, phase, run_status=RUN_STATUS_FAILED)

    async def _emit_awaiting_user_run(self, emit: EmitEvent, run_id: str, phase: Phase | None) -> None:
        await self._emit_run_complete(emit, run_id, phase, run_status=RUN_STATUS_AWAITING_USER)

    async def _emit_run_complete(
        self,
        emit: EmitEvent,
        run_id: str,
        phase: Phase | None,
        *,
        run_status: RunStatus,
    ) -> None:
        await emit(EventType.RUN_COMPLETE, run_id, phase, {"status": run_status.value})

    def _reset_active_workflow(self, runtime: SessionRuntime) -> None:
        state = runtime.state
        state.phase = Phase.BRIEF
        state.stage = WorkflowStage.COLLECTING_BRIEF
        state.brief = BlogBrief()
        state.transcript = []
        state.sources = []
        state.outline = None
        state.latest_draft = None
        state.last_user_message = None

    def _append_transcript(self, state: SessionState, role: str, text: str) -> None:
        stripped = text.strip()
        if not stripped:
            return
        state.transcript.append(TranscriptMessage(role=role, text=stripped))

    @staticmethod
    def _coerce_output(runner_output: Any, model_type: type[ModelT]) -> ModelT:
        final_output = getattr(runner_output, "final_output", runner_output)
        if isinstance(final_output, model_type):
            return final_output
        return model_type.model_validate(final_output)

    def _chunk_markdown(self, markdown: str, chunk_size: int) -> list[str]:
        return [markdown[index : index + chunk_size] for index in range(0, len(markdown), chunk_size)] or [""]
