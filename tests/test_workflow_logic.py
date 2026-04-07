from __future__ import annotations

import asyncio

from blog_agent.agent.blog_agent import BlogWorkflowService
from blog_agent.models import (
    ArtifactReview,
    BlogBrief,
    DraftPayload,
    ManagerDecision,
    OutlinePayload,
    OutlineSection,
    Phase,
    ResearchSource,
    SessionRuntime,
    SessionState,
    WorkflowStage,
)


def make_service() -> BlogWorkflowService:
    service = BlogWorkflowService.__new__(BlogWorkflowService)
    service.model = "test-model"
    return service


def make_runtime() -> SessionRuntime:
    return SessionRuntime(SessionState(session_id="session-1"))


def bind(service: BlogWorkflowService, name: str, func) -> None:
    setattr(service, name, func.__get__(service, BlogWorkflowService))


def sample_source() -> ResearchSource:
    return ResearchSource(title="Source", url="https://example.com/source", snippet="Snippet", content_excerpt="Facts")


def sample_outline(title: str = "Outline") -> OutlinePayload:
    return OutlinePayload(
        title=title,
        sections=[OutlineSection(heading="Intro", bullets=["Point one"])],
        sources=[sample_source()],
    )


def sample_draft(markdown: str = "# Draft") -> DraftPayload:
    return DraftPayload(markdown=markdown, sources=[sample_source()])


async def collect_events(service: BlogWorkflowService, runtime: SessionRuntime, text: str) -> list[dict]:
    events: list[dict] = []

    async def emit(event_type: str, run_id: str | None, phase: Phase | None, data: dict) -> None:
        events.append({"type": event_type, "run_id": run_id, "phase": phase, "data": data})

    await service.handle_user_message(runtime, text, emit)
    return events


def non_internal_event_types(events: list[dict]) -> list[str]:
    return [event["type"] for event in events if event["type"] != "internal_message"]


def internal_messages(events: list[dict]) -> list[str]:
    return [str(event["data"]["message"]) for event in events if event["type"] == "internal_message"]


def first_event(events: list[dict], event_type: str) -> dict:
    return next(event for event in events if event["type"] == event_type)


def test_incomplete_brief_leads_to_manager_clarification_only() -> None:
    asyncio.run(_test_incomplete_brief_leads_to_manager_clarification_only())


async def _test_incomplete_brief_leads_to_manager_clarification_only() -> None:
    service = make_service()
    runtime = make_runtime()

    async def _run_manager_decision(self, runtime, text):
        return ManagerDecision(
            action="ask_clarification",
            brief=BlogBrief(),
            assistant_message="What topic should this blog cover, and who is it for?",
            reply_kind="info",
        )

    async def _run_outline_writer(self, **kwargs):
        raise AssertionError("Writer should not run when clarification is needed.")

    bind(service, "_run_manager_decision", _run_manager_decision)
    bind(service, "_run_outline_writer", _run_outline_writer)

    events = await collect_events(service, runtime, "Write me a blog")

    assert non_internal_event_types(events) == ["assistant_message", "run_complete"]
    assert internal_messages(events) == ["Reviewing your request..."]
    assert runtime.state.stage == WorkflowStage.COLLECTING_BRIEF


def test_complete_brief_generates_outline_after_manager_review() -> None:
    asyncio.run(_test_complete_brief_generates_outline_after_manager_review())


async def _test_complete_brief_generates_outline_after_manager_review() -> None:
    service = make_service()
    runtime = make_runtime()
    calls: list[str] = []

    async def _run_manager_decision(self, runtime, text):
        return ManagerDecision(
            action="create_outline",
            brief=BlogBrief(
                topic="AI workflows for SEO teams",
                target_audience="content leads",
                goal_or_cta="book a demo",
                length_preference="1200 words",
            ),
            assistant_message="",
            reply_kind="info",
        )

    async def _run_outline_writer(self, **kwargs):
        calls.append("writer_outline")
        return sample_outline()

    async def _review_outline_with_manager(self, brief, outline, transcript):
        calls.append("review_outline")
        return ArtifactReview(action="approve", assistant_message="I have an outline ready.")

    bind(service, "_run_manager_decision", _run_manager_decision)
    bind(service, "_run_outline_writer", _run_outline_writer)
    bind(service, "_review_outline_with_manager", _review_outline_with_manager)

    events = await collect_events(service, runtime, "Write about AI workflows for SEO teams.")

    assert calls == ["writer_outline", "review_outline"]
    assert non_internal_event_types(events) == ["assistant_message", "artifact_ready", "run_complete"]
    assert internal_messages(events) == [
        "Reviewing your request...",
        "Creating the outline...",
        "Reviewing the outline...",
    ]
    assert first_event(events, "artifact_ready")["data"]["kind"] == "outline"
    assert runtime.state.stage == WorkflowStage.AWAITING_OUTLINE_FEEDBACK


def test_outline_feedback_triggers_outline_revision() -> None:
    asyncio.run(_test_outline_feedback_triggers_outline_revision())


async def _test_outline_feedback_triggers_outline_revision() -> None:
    service = make_service()
    runtime = make_runtime()
    runtime.state.outline = sample_outline("Old outline")
    runtime.state.sources = [sample_source()]
    runtime.state.stage = WorkflowStage.AWAITING_OUTLINE_FEEDBACK
    captured: list[str] = []

    async def _run_manager_decision(self, runtime, text):
        return ManagerDecision(
            action="revise_outline",
            brief=BlogBrief(
                topic="AI workflows for SEO teams",
                target_audience="content leads",
                goal_or_cta="book a demo",
                length_preference="1200 words",
            ),
            assistant_message="",
            revision_instructions="Make the intro sharper and add a measurement section.",
            reply_kind="info",
        )

    async def _run_outline_writer(self, **kwargs):
        captured.append(kwargs["revision_instructions"])
        return sample_outline("Revised outline")

    async def _review_outline_with_manager(self, brief, outline, transcript):
        return ArtifactReview(action="approve", assistant_message="I revised the outline.")

    bind(service, "_run_manager_decision", _run_manager_decision)
    bind(service, "_run_outline_writer", _run_outline_writer)
    bind(service, "_review_outline_with_manager", _review_outline_with_manager)

    events = await collect_events(service, runtime, "Please revise the outline.")

    assert captured == ["Make the intro sharper and add a measurement section."]
    assert internal_messages(events) == [
        "Reviewing your outline feedback...",
        "Revising the outline...",
        "Reviewing the outline...",
    ]
    assert first_event(events, "artifact_ready")["data"]["kind"] == "outline"


def test_outline_revision_without_existing_outline_fails_cleanly() -> None:
    asyncio.run(_test_outline_revision_without_existing_outline_fails_cleanly())


async def _test_outline_revision_without_existing_outline_fails_cleanly() -> None:
    service = make_service()
    runtime = make_runtime()

    async def _run_manager_decision(self, runtime, text):
        return ManagerDecision(
            action="revise_outline",
            brief=BlogBrief(topic="AI workflows"),
            assistant_message="",
            revision_instructions="Tighten the intro.",
            reply_kind="info",
        )

    bind(service, "_run_manager_decision", _run_manager_decision)

    events = await collect_events(service, runtime, "Please revise the outline.")

    assert non_internal_event_types(events) == ["error", "run_complete"]
    assert internal_messages(events) == ["Reviewing your request..."]
    assert first_event(events, "error")["data"]["message"] == "No outline is available to revise."
    assert first_event(events, "run_complete")["data"]["status"] == "failed"


def test_outline_approval_triggers_draft_generation() -> None:
    asyncio.run(_test_outline_approval_triggers_draft_generation())


async def _test_outline_approval_triggers_draft_generation() -> None:
    service = make_service()
    runtime = make_runtime()
    runtime.state.outline = sample_outline()
    runtime.state.sources = [sample_source()]
    runtime.state.stage = WorkflowStage.AWAITING_OUTLINE_FEEDBACK

    async def _run_manager_decision(self, runtime, text):
        return ManagerDecision(
            action="approve_outline_and_write_draft",
            brief=BlogBrief(
                topic="AI workflows for SEO teams",
                target_audience="content leads",
                goal_or_cta="book a demo",
                length_preference="1200 words",
            ),
            assistant_message="",
            reply_kind="info",
        )

    async def _run_draft_writer(self, **kwargs):
        return sample_draft("# Final draft")

    async def _review_draft_with_manager(self, brief, outline, draft, transcript):
        return ArtifactReview(action="approve", assistant_message="I have a draft ready.")

    bind(service, "_run_manager_decision", _run_manager_decision)
    bind(service, "_run_draft_writer", _run_draft_writer)
    bind(service, "_review_draft_with_manager", _review_draft_with_manager)

    events = await collect_events(service, runtime, "Approve the outline.")

    assert non_internal_event_types(events) == ["assistant_message", "artifact_delta", "artifact_ready", "run_complete"]
    assert internal_messages(events) == [
        "Reviewing your outline feedback...",
        "Writing the draft...",
        "Reviewing the draft...",
    ]
    assert first_event(events, "artifact_ready")["data"]["kind"] == "draft"
    assert runtime.state.stage == WorkflowStage.AWAITING_DRAFT_FEEDBACK


def test_post_draft_feedback_revises_current_draft() -> None:
    asyncio.run(_test_post_draft_feedback_revises_current_draft())


async def _test_post_draft_feedback_revises_current_draft() -> None:
    service = make_service()
    runtime = make_runtime()
    runtime.state.outline = sample_outline()
    runtime.state.latest_draft = sample_draft("# Old draft")
    runtime.state.sources = [sample_source()]
    runtime.state.stage = WorkflowStage.AWAITING_DRAFT_FEEDBACK
    captured: list[str] = []

    async def _run_manager_decision(self, runtime, text):
        return ManagerDecision(
            action="revise_draft",
            brief=BlogBrief(
                topic="AI workflows for SEO teams",
                target_audience="content leads",
                goal_or_cta="book a demo",
                length_preference="1200 words",
            ),
            assistant_message="",
            revision_instructions="Make the tone more practical and tighten the intro.",
            reply_kind="info",
        )

    async def _run_draft_writer(self, **kwargs):
        captured.append(kwargs["revision_instructions"])
        return sample_draft("# Revised draft")

    async def _review_draft_with_manager(self, brief, outline, draft, transcript):
        return ArtifactReview(action="approve", assistant_message="I revised the draft.")

    bind(service, "_run_manager_decision", _run_manager_decision)
    bind(service, "_run_draft_writer", _run_draft_writer)
    bind(service, "_review_draft_with_manager", _review_draft_with_manager)

    events = await collect_events(service, runtime, "Please make it more practical.")

    assert captured == ["Make the tone more practical and tighten the intro."]
    assert internal_messages(events) == [
        "Reviewing your draft feedback...",
        "Revising the draft...",
        "Reviewing the draft...",
    ]
    assert first_event(events, "artifact_ready")["data"]["kind"] == "draft"


def test_draft_revision_without_existing_draft_fails_cleanly() -> None:
    asyncio.run(_test_draft_revision_without_existing_draft_fails_cleanly())


async def _test_draft_revision_without_existing_draft_fails_cleanly() -> None:
    service = make_service()
    runtime = make_runtime()
    runtime.state.outline = sample_outline()

    async def _run_manager_decision(self, runtime, text):
        return ManagerDecision(
            action="revise_draft",
            brief=BlogBrief(topic="AI workflows"),
            assistant_message="",
            revision_instructions="Tighten the ending.",
            reply_kind="info",
        )

    bind(service, "_run_manager_decision", _run_manager_decision)

    events = await collect_events(service, runtime, "Please revise the draft.")

    assert non_internal_event_types(events) == ["error", "run_complete"]
    assert internal_messages(events) == ["Reviewing your request..."]
    assert first_event(events, "error")["data"]["message"] == "No draft is available to revise."
    assert first_event(events, "run_complete")["data"]["status"] == "failed"


def test_explicit_new_blog_resets_state_and_reprocesses() -> None:
    asyncio.run(_test_explicit_new_blog_resets_state_and_reprocesses())


async def _test_explicit_new_blog_resets_state_and_reprocesses() -> None:
    service = make_service()
    runtime = make_runtime()
    runtime.state.brief = BlogBrief(topic="Old topic")
    runtime.state.outline = sample_outline("Old outline")
    runtime.state.latest_draft = sample_draft("# Old draft")
    runtime.state.transcript = []
    decisions = [
        ManagerDecision(action="start_new_blog", brief=BlogBrief(topic="New topic"), assistant_message="", reply_kind="info"),
        ManagerDecision(action="ask_clarification", brief=BlogBrief(topic="New topic"), assistant_message="Who is the new blog for?", reply_kind="info"),
    ]

    async def _run_manager_decision(self, runtime, text):
        return decisions.pop(0)

    bind(service, "_run_manager_decision", _run_manager_decision)

    events = await collect_events(service, runtime, "Start a new blog about API pricing.")

    assert runtime.state.outline is None
    assert runtime.state.latest_draft is None
    assert runtime.state.brief.topic == "New topic"
    assert [message.text for message in runtime.state.transcript] == [
        "Start a new blog about API pricing.",
        "Who is the new blog for?",
    ]
    assert non_internal_event_types(events) == ["assistant_message", "run_complete"]
    assert internal_messages(events) == [
        "Reviewing your request...",
        "Reviewing your request...",
    ]


def test_research_failure_surfaces_manager_authored_reply() -> None:
    asyncio.run(_test_research_failure_surfaces_manager_authored_reply())


async def _test_research_failure_surfaces_manager_authored_reply() -> None:
    service = make_service()
    runtime = make_runtime()

    async def _run_manager_decision(self, runtime, text):
        return ManagerDecision(
            action="create_outline",
            brief=BlogBrief(
                topic="AI workflows for SEO teams",
                target_audience="content leads",
                goal_or_cta="book a demo",
                length_preference="1200 words",
            ),
            assistant_message="",
            reply_kind="info",
        )

    async def _run_outline_writer(self, **kwargs):
        return OutlinePayload(title="Outline", sections=[OutlineSection(heading="Intro", bullets=["Point"])], sources=[])

    async def _compose_failure_message(self, runtime, error_message):
        return "I couldn’t gather supporting sources. Try again or tell me to proceed without research."

    bind(service, "_run_manager_decision", _run_manager_decision)
    bind(service, "_run_outline_writer", _run_outline_writer)
    bind(service, "_compose_failure_message", _compose_failure_message)

    events = await collect_events(service, runtime, "Write a researched blog about AI workflows.")

    assert non_internal_event_types(events) == ["assistant_message", "run_complete"]
    assert internal_messages(events) == [
        "Reviewing your request...",
        "Creating the outline...",
    ]
    assert first_event(events, "assistant_message")["data"]["message"].startswith("I couldn’t gather supporting sources")
    assert first_event(events, "run_complete")["data"]["status"] == "failed"


def test_outline_review_retries_once_before_delivery() -> None:
    asyncio.run(_test_outline_review_retries_once_before_delivery())


async def _test_outline_review_retries_once_before_delivery() -> None:
    service = make_service()
    runtime = make_runtime()
    outline_calls = 0
    review_calls = 0

    async def _run_manager_decision(self, runtime, text):
        return ManagerDecision(
            action="create_outline",
            brief=BlogBrief(
                topic="AI workflows for SEO teams",
                target_audience="content leads",
                goal_or_cta="book a demo",
                length_preference="1200 words",
            ),
            assistant_message="",
            reply_kind="info",
        )

    async def _run_outline_writer(self, **kwargs):
        nonlocal outline_calls
        outline_calls += 1
        return sample_outline(f"Outline {outline_calls}")

    async def _review_outline_with_manager(self, brief, outline, transcript):
        nonlocal review_calls
        review_calls += 1
        if review_calls == 1:
            return ArtifactReview(action="revise", revision_instructions="Tighten the angle.")
        return ArtifactReview(action="approve", assistant_message="I have an outline ready.")

    bind(service, "_run_manager_decision", _run_manager_decision)
    bind(service, "_run_outline_writer", _run_outline_writer)
    bind(service, "_review_outline_with_manager", _review_outline_with_manager)

    events = await collect_events(service, runtime, "Write about AI workflows.")

    assert outline_calls == 2
    assert review_calls == 2
    assert non_internal_event_types(events) == ["assistant_message", "artifact_ready", "run_complete"]
    assert internal_messages(events) == [
        "Reviewing your request...",
        "Creating the outline...",
        "Reviewing the outline...",
        "Revising the outline...",
        "Reviewing the outline...",
    ]


def test_draft_review_retries_once_before_delivery() -> None:
    asyncio.run(_test_draft_review_retries_once_before_delivery())


async def _test_draft_review_retries_once_before_delivery() -> None:
    service = make_service()
    runtime = make_runtime()
    runtime.state.outline = sample_outline()
    runtime.state.sources = [sample_source()]
    runtime.state.stage = WorkflowStage.AWAITING_OUTLINE_FEEDBACK
    draft_calls = 0
    review_calls = 0

    async def _run_manager_decision(self, runtime, text):
        return ManagerDecision(
            action="approve_outline_and_write_draft",
            brief=BlogBrief(
                topic="AI workflows for SEO teams",
                target_audience="content leads",
                goal_or_cta="book a demo",
                length_preference="1200 words",
            ),
            assistant_message="",
            reply_kind="info",
        )

    async def _run_draft_writer(self, **kwargs):
        nonlocal draft_calls
        draft_calls += 1
        return sample_draft(f"# Draft {draft_calls}")

    async def _review_draft_with_manager(self, brief, outline, draft, transcript):
        nonlocal review_calls
        review_calls += 1
        if review_calls == 1:
            return ArtifactReview(action="revise", revision_instructions="Strengthen the conclusion.")
        return ArtifactReview(action="approve", assistant_message="I have a draft ready.")

    bind(service, "_run_manager_decision", _run_manager_decision)
    bind(service, "_run_draft_writer", _run_draft_writer)
    bind(service, "_review_draft_with_manager", _review_draft_with_manager)

    events = await collect_events(service, runtime, "Approve the outline.")

    assert draft_calls == 2
    assert review_calls == 2
    assert non_internal_event_types(events) == ["assistant_message", "artifact_delta", "artifact_ready", "run_complete"]
    assert internal_messages(events) == [
        "Reviewing your outline feedback...",
        "Writing the draft...",
        "Reviewing the draft...",
        "Revising the draft...",
        "Reviewing the draft...",
    ]


def test_draft_review_can_retry_multiple_times_before_delivery() -> None:
    asyncio.run(_test_draft_review_can_retry_multiple_times_before_delivery())


async def _test_draft_review_can_retry_multiple_times_before_delivery() -> None:
    service = make_service()
    service.max_draft_review_revisions = 3
    runtime = make_runtime()
    runtime.state.outline = sample_outline()
    runtime.state.sources = [sample_source()]
    runtime.state.stage = WorkflowStage.AWAITING_OUTLINE_FEEDBACK
    draft_calls = 0
    review_calls = 0

    async def _run_manager_decision(self, runtime, text):
        return ManagerDecision(
            action="approve_outline_and_write_draft",
            brief=BlogBrief(
                topic="AI workflows for SEO teams",
                target_audience="content leads",
                goal_or_cta="book a demo",
                length_preference="1200 words",
            ),
            assistant_message="",
            reply_kind="info",
        )

    async def _run_draft_writer(self, **kwargs):
        nonlocal draft_calls
        draft_calls += 1
        return sample_draft(f"# Draft {draft_calls}")

    async def _review_draft_with_manager(self, brief, outline, draft, transcript):
        nonlocal review_calls
        review_calls += 1
        if review_calls < 4:
            return ArtifactReview(action="revise", revision_instructions=f"Revision pass {review_calls}")
        return ArtifactReview(action="approve", assistant_message="I have a draft ready.")

    bind(service, "_run_manager_decision", _run_manager_decision)
    bind(service, "_run_draft_writer", _run_draft_writer)
    bind(service, "_review_draft_with_manager", _review_draft_with_manager)

    events = await collect_events(service, runtime, "Approve the outline.")

    assert draft_calls == 4
    assert review_calls == 4
    assert non_internal_event_types(events) == ["assistant_message", "artifact_delta", "artifact_ready", "run_complete"]
    assert internal_messages(events) == [
        "Reviewing your outline feedback...",
        "Writing the draft...",
        "Reviewing the draft...",
        "Revising the draft...",
        "Reviewing the draft...",
        "Revising the draft...",
        "Reviewing the draft...",
        "Revising the draft...",
        "Reviewing the draft...",
    ]


def test_draft_review_exhaustion_does_not_emit_review_commentary() -> None:
    asyncio.run(_test_draft_review_exhaustion_does_not_emit_review_commentary())


async def _test_draft_review_exhaustion_does_not_emit_review_commentary() -> None:
    service = make_service()
    service.max_draft_review_revisions = 1
    runtime = make_runtime()
    runtime.state.outline = sample_outline()
    runtime.state.sources = [sample_source()]
    runtime.state.stage = WorkflowStage.AWAITING_OUTLINE_FEEDBACK
    draft_calls = 0
    review_calls = 0

    async def _run_manager_decision(self, runtime, text):
        return ManagerDecision(
            action="approve_outline_and_write_draft",
            brief=BlogBrief(
                topic="AI workflows for SEO teams",
                target_audience="content leads",
                goal_or_cta="book a demo",
                length_preference="1200 words",
            ),
            assistant_message="",
            reply_kind="info",
        )

    async def _run_draft_writer(self, **kwargs):
        nonlocal draft_calls
        draft_calls += 1
        return sample_draft(f"# Draft {draft_calls}")

    async def _review_draft_with_manager(self, brief, outline, draft, transcript):
        nonlocal review_calls
        review_calls += 1
        return ArtifactReview(action="revise", assistant_message="This should stay hidden.", revision_instructions="Make it tighter.")

    bind(service, "_run_manager_decision", _run_manager_decision)
    bind(service, "_run_draft_writer", _run_draft_writer)
    bind(service, "_review_draft_with_manager", _review_draft_with_manager)

    events = await collect_events(service, runtime, "Approve the outline.")

    assert draft_calls == 2
    assert review_calls == 2
    assert non_internal_event_types(events) == ["assistant_message", "artifact_delta", "artifact_ready", "run_complete"]
    assert internal_messages(events) == [
        "Reviewing your outline feedback...",
        "Writing the draft...",
        "Reviewing the draft...",
        "Revising the draft...",
        "Reviewing the draft...",
    ]
    assert first_event(events, "assistant_message")["data"]["message"] == (
        "I revised the draft and this is the strongest version from the current pass. "
        "Tell me what to revise or ask for a new blog."
    )
    assert "This should stay hidden." not in str(first_event(events, "assistant_message")["data"]["message"])
    assert first_event(events, "artifact_ready")["data"]["kind"] == "draft"
    assert first_event(events, "run_complete")["data"]["status"] == "awaiting_user"


def test_draft_review_stops_without_exposing_commentary_after_retry_budget() -> None:
    asyncio.run(_test_draft_review_stops_without_exposing_commentary_after_retry_budget())


async def _test_draft_review_stops_without_exposing_commentary_after_retry_budget() -> None:
    service = make_service()
    runtime = make_runtime()
    runtime.state.outline = sample_outline()
    runtime.state.sources = [sample_source()]
    runtime.state.stage = WorkflowStage.AWAITING_OUTLINE_FEEDBACK
    draft_calls = 0

    async def _run_manager_decision(self, runtime, text):
        return ManagerDecision(
            action="approve_outline_and_write_draft",
            brief=BlogBrief(
                topic="AI workflows for SEO teams",
                target_audience="content leads",
                goal_or_cta="book a demo",
                length_preference="1200 words",
            ),
            assistant_message="",
            reply_kind="info",
        )

    async def _run_draft_writer(self, **kwargs):
        nonlocal draft_calls
        draft_calls += 1
        return sample_draft(f"# Draft {draft_calls}")

    async def _review_draft_with_manager(self, brief, outline, draft, transcript):
        return ArtifactReview(
            action="revise",
            assistant_message="The draft still needs a stronger ending.",
            revision_instructions="Strengthen the ending.",
        )

    bind(service, "_run_manager_decision", _run_manager_decision)
    bind(service, "_run_draft_writer", _run_draft_writer)
    bind(service, "_review_draft_with_manager", _review_draft_with_manager)

    events = await collect_events(service, runtime, "Approve the outline.")

    assert draft_calls == service.max_draft_review_revisions + 1
    assert non_internal_event_types(events) == ["assistant_message", "artifact_delta", "artifact_ready", "run_complete"]
    assert internal_messages(events) == [
        "Reviewing your outline feedback...",
        "Writing the draft...",
        "Reviewing the draft...",
        "Revising the draft...",
        "Reviewing the draft...",
    ]
    assert first_event(events, "assistant_message")["data"]["message"] == (
        "I revised the draft and this is the strongest version from the current pass. "
        "Tell me what to revise or ask for a new blog."
    )
    assert "stronger ending" not in str(first_event(events, "assistant_message")["data"]["message"]).lower()
    assert first_event(events, "artifact_ready")["data"]["kind"] == "draft"
    assert first_event(events, "run_complete")["data"]["status"] == "awaiting_user"
    assert runtime.state.stage == WorkflowStage.AWAITING_DRAFT_FEEDBACK
