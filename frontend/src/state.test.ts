import { appReducer, createInitialState } from "./state";
import type { BaseEventEnvelope } from "./types";

function makeEvent(overrides: Partial<BaseEventEnvelope>): BaseEventEnvelope {
  return {
    type: "assistant_message",
    session_id: "session-1",
    run_id: "run-1",
    phase: "brief",
    data: {},
    ...overrides,
  };
}

describe("appReducer", () => {
  it("accumulates draft artifact deltas and replaces them with the final draft payload", () => {
    const initial = createInitialState("session-1");
    const afterFirstDelta = appReducer(initial, {
      type: "event_received",
      event: makeEvent({
        type: "artifact_delta",
        phase: "draft",
        data: { kind: "draft", delta: "# Hello" },
      }),
      receivedAt: "2026-01-01T00:00:00.000Z",
    });

    const afterSecondDelta = appReducer(afterFirstDelta, {
      type: "event_received",
      event: makeEvent({
        type: "artifact_delta",
        phase: "draft",
        data: { kind: "draft", delta: "\n\nWorld" },
      }),
      receivedAt: "2026-01-01T00:00:01.000Z",
    });

    const finalState = appReducer(afterSecondDelta, {
      type: "event_received",
      event: makeEvent({
        type: "artifact_ready",
        phase: "draft",
        data: {
          kind: "draft",
          payload: { markdown: "# Final", sources: [] },
        },
      }),
      receivedAt: "2026-01-01T00:00:02.000Z",
    });

    const streamedDraft = afterSecondDelta.conversation[afterSecondDelta.conversation.length - 1];
    const finalDraft = finalState.conversation[finalState.conversation.length - 1];

    expect(streamedDraft.kind).toBe("artifact");
    if (streamedDraft.kind === "artifact" && streamedDraft.artifactKind === "draft") {
      expect(streamedDraft.payload.markdown).toBe("# Hello\n\nWorld");
      expect(streamedDraft.streaming).toBe(true);
    }

    expect(finalDraft.kind).toBe("artifact");
    if (finalDraft.kind === "artifact" && finalDraft.artifactKind === "draft") {
      expect(finalDraft.payload.markdown).toBe("# Final");
      expect(finalDraft.streaming).toBe(false);
    }
  });

  it("records outline artifacts and waits for user feedback", () => {
    const initial = createInitialState("session-1");
    const next = appReducer(initial, {
      type: "event_received",
      event: makeEvent({
        type: "artifact_ready",
        phase: "outline",
        data: {
          kind: "outline",
          payload: { title: "Draft title", sections: [], sources: [] },
        },
      }),
      receivedAt: "2026-01-01T00:00:00.000Z",
    });

    const finalState = appReducer(next, {
      type: "event_received",
      event: makeEvent({
        type: "run_complete",
        phase: "outline",
        data: { status: "awaiting_user" },
      }),
      receivedAt: "2026-01-01T00:00:01.000Z",
    });

    expect(next.pendingAction).toBe("outline_feedback");
    expect(finalState.runState.status).toBe("paused");
    expect(finalState.statusLine).toContain("Waiting for your next message");
  });

  it("adds assistant replies to the conversation thread", () => {
    const initial = createInitialState("session-1");
    const next = appReducer(initial, {
      type: "event_received",
      event: makeEvent({
        type: "assistant_message",
        data: { message: "I have enough to draft an outline." },
      }),
      receivedAt: "2026-01-01T00:00:00.000Z",
    });

    const lastItem = next.conversation[next.conversation.length - 1];
    expect(lastItem.kind).toBe("message");
    if (lastItem.kind === "message") {
      expect(lastItem.role).toBe("assistant");
      expect(lastItem.text).toBe("I have enough to draft an outline.");
    }
  });

  it("keeps internal review messages out of the visible conversation", () => {
    const initial = createInitialState("session-1");
    const next = appReducer(initial, {
      type: "event_received",
      event: makeEvent({
        type: "internal_message",
        data: { message: "This is private review feedback." },
      }),
      receivedAt: "2026-01-01T00:00:00.000Z",
    });

    expect(next.conversation).toHaveLength(1);
    expect(next.conversation[0].kind).toBe("message");
    if (next.conversation[0].kind === "message") {
      expect(next.conversation[0].text).toBe(
        "Describe the blog you want to write. I’ll clarify what is missing, propose an outline, draft the post, and revise it through normal chat messages.",
      );
    }
    expect(next.statusLine).toBe("This is private review feedback.");
  });

  it("shows immediate status when the user sends outline or draft feedback", () => {
    const outlineState = appReducer(
      {
        ...createInitialState("session-1"),
        pendingAction: "outline_feedback",
      },
      {
        type: "user_message_sent",
        text: "Please tighten the intro.",
      },
    );

    const draftState = appReducer(
      {
        ...createInitialState("session-1"),
        pendingAction: "draft_feedback",
      },
      {
        type: "user_message_sent",
        text: "Make it more practical.",
      },
    );

    const generalState = appReducer(createInitialState("session-1"), {
      type: "user_message_sent",
      text: "Write about AI workflows.",
    });

    expect(outlineState.statusLine).toBe("Reviewing your outline feedback...");
    expect(draftState.statusLine).toBe("Reviewing your draft feedback...");
    expect(generalState.statusLine).toBe("Reviewing your request...");
  });
});
