from __future__ import annotations

from blog_agent.agent.prompts import (
    AI_SIGNAL_REMOVAL_CHECKLIST,
    DRAFT_QUALITY_RULES,
    HOOK_RULES,
    STYLE_IDENTITY,
    build_draft_review_prompt,
    build_manager_decision_prompt,
    build_writer_draft_prompt,
    build_writer_draft_revision_prompt,
)
from blog_agent.models import (
    BlogBrief,
    DraftPayload,
    OutlinePayload,
    OutlineSection,
    ResearchSource,
    TranscriptMessage,
    WorkflowStage,
)


def sample_brief() -> BlogBrief:
    return BlogBrief(
        topic="AI workflows for SEO teams",
        target_audience="content leads",
        goal_or_cta="book a demo",
        length_preference="1200 words",
        seo_keywords=["AI workflows", "SEO automation"],
    )


def sample_outline() -> OutlinePayload:
    return OutlinePayload(
        title="How AI Workflows Help SEO Teams Ship Better Content",
        sections=[OutlineSection(heading="Why this matters", bullets=["Point one"])],
        sources=[sample_source()],
    )


def sample_draft() -> DraftPayload:
    return DraftPayload(markdown="# Draft\n\nUseful draft content.", sources=[sample_source()])


def sample_source() -> ResearchSource:
    return ResearchSource(
        title="Example Source",
        url="https://example.com/source",
        snippet="Helpful snippet",
        content_excerpt="Useful evidence",
    )


def sample_transcript() -> list[TranscriptMessage]:
    return [TranscriptMessage(role="user", text="Write a practical B2B blog post.")]


def test_writer_draft_prompt_includes_human_style_rules() -> None:
    prompt = build_writer_draft_prompt(
        brief=sample_brief(),
        outline=sample_outline(),
        sources=[sample_source()],
    )

    assert STYLE_IDENTITY not in prompt
    assert DRAFT_QUALITY_RULES in prompt
    assert HOOK_RULES in prompt
    assert AI_SIGNAL_REMOVAL_CHECKLIST in prompt
    assert "knowledgeable human writer" in prompt
    assert "Avoid em dashes." in prompt
    assert "Start the article with 3 concise hook options" in prompt


def test_writer_draft_revision_prompt_includes_self_edit_rules() -> None:
    prompt = build_writer_draft_revision_prompt(
        brief=sample_brief(),
        outline=sample_outline(),
        draft=sample_draft(),
        revision_instructions="Tighten the intro and make the tone more practical.",
        sources=[sample_source()],
    )

    assert DRAFT_QUALITY_RULES in prompt
    assert HOOK_RULES in prompt
    assert AI_SIGNAL_REMOVAL_CHECKLIST in prompt
    assert "remove obvious AI-sounding language" in prompt
    assert "Preserve what already works." in prompt
    assert "Do not use made-up scenes" in prompt


def test_draft_review_prompt_enforces_human_quality_checks() -> None:
    prompt = build_draft_review_prompt(
        brief=sample_brief(),
        outline=sample_outline(),
        draft=sample_draft(),
        transcript=sample_transcript(),
    )

    assert STYLE_IDENTITY in prompt
    assert DRAFT_QUALITY_RULES in prompt
    assert HOOK_RULES in prompt
    assert AI_SIGNAL_REMOVAL_CHECKLIST in prompt
    assert "robotic transitions" in prompt
    assert "overused em dashes, colons, or semicolons" in prompt
    assert "realistic, non-fabricated hook" in prompt
    assert "at most one refinement round per artifact" in prompt
    assert "Do not ask for a second rewrite" in prompt


def test_manager_decision_prompt_excludes_draft_style_policy() -> None:
    prompt = build_manager_decision_prompt(
        stage=WorkflowStage.COLLECTING_BRIEF,
        user_message="Write a blog post about AI workflows.",
        brief=sample_brief(),
        outline=None,
        draft=None,
        sources=[sample_source()],
        transcript=sample_transcript(),
    )

    assert STYLE_IDENTITY not in prompt
    assert DRAFT_QUALITY_RULES not in prompt
    assert HOOK_RULES not in prompt
    assert AI_SIGNAL_REMOVAL_CHECKLIST not in prompt
    assert "robotic transitions" not in prompt
