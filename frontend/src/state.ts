import type {
  BaseEventEnvelope,
  ConversationItem,
  DraftConversationItem,
  DraftPayload,
  EventLogItem,
  OutlinePayload,
  RunState,
} from "./types";

export type ConnectionState = "connecting" | "connected" | "disconnected" | "error";

export interface AppState {
  connectionState: ConnectionState;
  sessionId: string;
  conversation: ConversationItem[];
  eventLog: EventLogItem[];
  runState: RunState;
  statusLine: string;
  pendingAction: "outline_feedback" | "draft_feedback" | null;
}

export type AppAction =
  | { type: "socket_connecting" }
  | { type: "socket_open" }
  | { type: "socket_closed" }
  | { type: "socket_error"; message: string }
  | { type: "user_message_sent"; text: string }
  | { type: "event_received"; event: BaseEventEnvelope; receivedAt: string };

export function createInitialState(sessionId: string): AppState {
  return {
    connectionState: "connecting",
    sessionId,
    conversation: [
      {
        id: createId("intro"),
        kind: "message",
        role: "assistant",
        variant: "status",
        text: "Describe the blog you want to write. I’ll clarify what is missing, propose an outline, draft the post, and revise it through normal chat messages.",
      },
    ],
    eventLog: [],
    runState: {
      runId: null,
      phase: "brief",
      status: "idle",
    },
    statusLine: "Connecting to the assistant...",
    pendingAction: null,
  };
}

export function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "socket_connecting":
      return {
        ...state,
        connectionState: "connecting",
        statusLine: "Connecting to the assistant...",
      };
    case "socket_open":
      return {
        ...state,
        connectionState: "connected",
        statusLine: "Connected. Send a message to begin.",
      };
    case "socket_closed":
      return {
        ...state,
        connectionState: "disconnected",
        statusLine: "Connection closed.",
      };
    case "socket_error":
      return withAssistantMessage(
        {
          ...state,
          connectionState: "error",
          statusLine: action.message,
        },
        action.message,
        "error",
      );
    case "user_message_sent":
      return {
        ...state,
        conversation: [
          ...state.conversation,
          {
            id: createId("user"),
            kind: "message",
            role: "user",
            text: action.text,
            variant: "default",
          },
        ],
        runState: {
          ...state.runState,
          status: "running",
        },
        statusLine: pendingActionStatus(state.pendingAction),
        pendingAction: null,
      };
    case "event_received":
      return reduceIncomingEvent(state, action.event, action.receivedAt);
    default:
      return state;
  }
}

function reduceIncomingEvent(state: AppState, event: BaseEventEnvelope, receivedAt: string): AppState {
  const nextState: AppState = {
    ...state,
    eventLog: [
      {
        ...event,
        receivedAt,
        id: createId("event"),
      },
      ...state.eventLog,
    ].slice(0, 50),
    runState: {
      runId: event.run_id,
      phase: event.phase,
      status: deriveRunStatus(state.runState.status, event.type, event.data),
    },
  };

  switch (event.type) {
    case "session_ready":
      return {
        ...nextState,
        connectionState: "connected",
        statusLine: "Ready for a new blog conversation.",
      };
    case "assistant_message":
      return withAssistantMessage(
        {
          ...nextState,
          statusLine: String(event.data.message ?? "Assistant replied."),
        },
        String(event.data.message ?? ""),
        "default",
      );
    case "internal_message":
      return {
        ...nextState,
        statusLine: String(event.data.message ?? "Working on your request..."),
      };
    case "artifact_delta":
      if (event.data.kind !== "draft") {
        return nextState;
      }
      return {
        ...nextState,
        conversation: appendDraftDelta(nextState.conversation, String(event.data.delta ?? "")),
        statusLine: "Drafting...",
      };
    case "artifact_ready":
      return reduceArtifactReady(nextState, event.data);
    case "searching":
      return {
        ...nextState,
        statusLine: "Researching supporting sources...",
      };
    case "tool_started":
      return {
        ...nextState,
        statusLine: `Running ${String(event.data.tool ?? "tool")}...`,
      };
    case "tool_completed":
      return {
        ...nextState,
        statusLine: `${String(event.data.tool ?? "Tool")} completed.`,
      };
    case "error":
      return withAssistantMessage(
        {
          ...nextState,
          statusLine: String(event.data.message ?? "The assistant reported an error."),
        },
        String(event.data.message ?? "The assistant reported an error."),
        "error",
      );
    case "run_complete":
      return {
        ...nextState,
        statusLine: completionMessage(event.data.status),
      };
    default:
      return nextState;
  }
}

function reduceArtifactReady(state: AppState, data: Record<string, unknown>): AppState {
  const kind = String(data.kind ?? "");
  const payload = typeof data.payload === "object" && data.payload ? data.payload as Record<string, unknown> : null;
  if (kind === "outline" && payload) {
    return {
      ...state,
      conversation: [
        ...state.conversation,
        {
          id: createId("outline"),
          kind: "artifact",
          artifactKind: "outline",
          payload: payload as unknown as OutlinePayload,
        },
      ],
      pendingAction: "outline_feedback",
      statusLine: "Outline ready.",
    };
  }
  if (kind === "draft" && payload) {
    return {
      ...state,
      conversation: finalizeDraftArtifact(
        state.conversation,
        payload as unknown as DraftPayload,
      ),
      pendingAction: "draft_feedback",
      statusLine: "Draft ready.",
    };
  }
  return state;
}

function appendDraftDelta(conversation: ConversationItem[], delta: string): ConversationItem[] {
  const nextConversation = [...conversation];
  const lastItem = nextConversation[nextConversation.length - 1];
  if (lastItem?.kind === "artifact" && lastItem.artifactKind === "draft" && lastItem.streaming) {
    nextConversation[nextConversation.length - 1] = {
      ...lastItem,
      payload: {
        ...lastItem.payload,
        markdown: `${lastItem.payload.markdown}${delta}`,
      },
    } satisfies DraftConversationItem;
    return nextConversation;
  }

  nextConversation.push({
    id: createId("draft"),
    kind: "artifact",
    artifactKind: "draft",
    payload: {
      markdown: delta,
      sources: [],
    },
    streaming: true,
  });
  return nextConversation;
}

function finalizeDraftArtifact(conversation: ConversationItem[], payload: DraftPayload): ConversationItem[] {
  const nextConversation = [...conversation];
  const lastItem = nextConversation[nextConversation.length - 1];
  if (lastItem?.kind === "artifact" && lastItem.artifactKind === "draft" && lastItem.streaming) {
    nextConversation[nextConversation.length - 1] = {
      ...lastItem,
      payload,
      streaming: false,
    } satisfies DraftConversationItem;
    return nextConversation;
  }

  nextConversation.push({
    id: createId("draft"),
    kind: "artifact",
    artifactKind: "draft",
    payload,
    streaming: false,
  });
  return nextConversation;
}

function deriveRunStatus(
  currentStatus: RunState["status"],
  eventType: BaseEventEnvelope["type"],
  data: Record<string, unknown>,
): RunState["status"] {
  if (eventType === "error") {
    return "failed";
  }
  if (eventType === "run_complete") {
    const status = String(data.status ?? "");
    if (status === "awaiting_user") {
      return "paused";
    }
    if (status === "cancelled") {
      return "cancelled";
    }
    if (status === "completed") {
      return "completed";
    }
    if (status === "failed") {
      return "failed";
    }
    return currentStatus;
  }
  if (eventType === "session_ready") {
    return "idle";
  }
  return "running";
}

function completionMessage(status: unknown): string {
  const normalized = String(status ?? "");
  if (normalized === "awaiting_user") {
    return "Waiting for your next message.";
  }
  if (normalized === "completed") {
    return "Run completed successfully.";
  }
  if (normalized === "cancelled") {
    return "Run cancelled.";
  }
  if (normalized === "failed") {
    return "Run failed.";
  }
  return "Run finished.";
}

function withAssistantMessage(
  state: AppState,
  text: string,
  variant: "default" | "status" | "error",
): AppState {
  if (!text.trim()) {
    return state;
  }
  return {
    ...state,
    conversation: [
      ...state.conversation,
      {
        id: createId("assistant"),
        kind: "message",
        role: "assistant",
        text,
        variant,
      },
    ],
  };
}

function createId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

function pendingActionStatus(pendingAction: AppState["pendingAction"]): string {
  if (pendingAction === "outline_feedback") {
    return "Reviewing your outline feedback...";
  }
  if (pendingAction === "draft_feedback") {
    return "Reviewing your draft feedback...";
  }
  return "Reviewing your request...";
}
