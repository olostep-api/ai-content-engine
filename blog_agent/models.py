from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Phase(str, Enum):
    BRIEF = "brief"
    RESEARCH = "research"
    OUTLINE = "outline"
    DRAFT = "draft"


class WorkflowStage(str, Enum):
    COLLECTING_BRIEF = "collecting_brief"
    AWAITING_OUTLINE_FEEDBACK = "awaiting_outline_feedback"
    DRAFTING = "drafting"
    AWAITING_DRAFT_FEEDBACK = "awaiting_draft_feedback"


class BlogBrief(BaseModel):
    topic: str | None = None
    target_audience: str | None = None
    goal_or_cta: str | None = None
    length_preference: str | None = None
    tone: str | None = None
    seo_keywords: list[str] = Field(default_factory=list)
    must_use_sources: bool = True

    model_config = {"extra": "forbid"}


class ClarificationQuestion(BaseModel):
    field: str
    question: str
    reason: str

    model_config = {"extra": "forbid"}


class ResearchSource(BaseModel):
    title: str
    url: str
    snippet: str = ""
    content_excerpt: str = ""

    model_config = {"extra": "forbid"}


class OutlineSection(BaseModel):
    heading: str
    bullets: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class OutlinePayload(BaseModel):
    title: str
    sections: list[OutlineSection] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class DraftPayload(BaseModel):
    markdown: str
    sources: list[ResearchSource] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class TranscriptMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str

    model_config = {"extra": "forbid"}


class ManagerDecision(BaseModel):
    action: Literal[
        "ask_clarification",
        "create_outline",
        "revise_outline",
        "approve_outline_and_write_draft",
        "revise_draft",
        "start_new_blog",
        "reply_with_error",
    ]
    brief: BlogBrief
    assistant_message: str = ""
    revision_instructions: str | None = None
    reply_kind: Literal["info", "error"] = "info"

    model_config = {"extra": "forbid"}


class ArtifactReview(BaseModel):
    action: Literal["approve", "revise", "reject"]
    assistant_message: str = ""
    revision_instructions: str | None = None

    model_config = {"extra": "forbid"}


class AssistantReply(BaseModel):
    assistant_message: str

    model_config = {"extra": "forbid"}


class EventEnvelope(BaseModel):
    type: str
    session_id: str
    run_id: str | None = None
    phase: Phase | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class UserMessage(BaseModel):
    type: Literal["user_message"]
    text: str


class CancelRun(BaseModel):
    type: Literal["cancel_run"]


ClientMessage = UserMessage | CancelRun


class SessionState(BaseModel):
    session_id: str
    phase: Phase = Phase.BRIEF
    stage: WorkflowStage = WorkflowStage.COLLECTING_BRIEF
    brief: BlogBrief = Field(default_factory=BlogBrief)
    transcript: list[TranscriptMessage] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)
    outline: OutlinePayload | None = None
    latest_draft: DraftPayload | None = None
    latest_run_id: str | None = None
    last_user_message: str | None = None

    model_config = {"arbitrary_types_allowed": True}


class SessionRuntime:
    def __init__(self, state: SessionState) -> None:
        self.state = state
        self.current_task: asyncio.Task[Any] | None = None
