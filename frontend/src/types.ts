export type Phase = "brief" | "research" | "outline" | "draft";

export interface ResearchSource {
  title: string;
  url: string;
  snippet?: string;
  content_excerpt?: string;
}

export interface OutlineSection {
  heading: string;
  bullets: string[];
}

export interface OutlinePayload {
  title: string;
  sections: OutlineSection[];
  sources: ResearchSource[];
}

export interface DraftPayload {
  markdown: string;
  sources: ResearchSource[];
}

export interface BaseEventEnvelope {
  type:
    | "session_ready"
    | "assistant_message"
    | "internal_message"
    | "artifact_ready"
    | "artifact_delta"
    | "error"
    | "run_complete"
    | "searching"
    | "tool_started"
    | "tool_completed";
  session_id: string;
  run_id: string | null;
  phase: Phase | null;
  data: Record<string, unknown>;
}

export interface ReceivedEvent extends BaseEventEnvelope {
  receivedAt: string;
}

export interface EventLogItem extends ReceivedEvent {
  id: string;
}

export type OutboundMessage =
  | {
      type: "user_message";
      text: string;
    }
  | {
      type: "cancel_run";
    };

export interface TextConversationItem {
  id: string;
  kind: "message";
  role: "user" | "assistant";
  text: string;
  variant: "default" | "status" | "error";
}

export interface OutlineConversationItem {
  id: string;
  kind: "artifact";
  artifactKind: "outline";
  payload: OutlinePayload;
}

export interface DraftConversationItem {
  id: string;
  kind: "artifact";
  artifactKind: "draft";
  payload: DraftPayload;
  streaming: boolean;
}

export type ConversationItem =
  | TextConversationItem
  | OutlineConversationItem
  | DraftConversationItem;

export interface RunState {
  runId: string | null;
  phase: Phase | null;
  status: "idle" | "running" | "paused" | "completed" | "failed" | "cancelled";
}
