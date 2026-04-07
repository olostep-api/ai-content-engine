import { useEffect, useMemo, useReducer, useRef, useState } from "react";

import { ChatComposer } from "./components/ChatComposer";
import { ConversationPanel } from "./components/ConversationPanel";
import { PhaseBadge } from "./components/PhaseBadge";
import { createSocketClient, type SocketClient } from "./lib/ws";
import { appReducer, createInitialState } from "./state";
import type { BaseEventEnvelope } from "./types";
import "./styles.css";

const SESSION_STORAGE_KEY = "blog-agent-session-id";
const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL ?? "ws://127.0.0.1:8000";

interface AppProps {
  clientFactory?: typeof createSocketClient;
  storage?: Storage;
}

export default function App({
  clientFactory = createSocketClient,
  storage = window.localStorage,
}: AppProps) {
  const sessionId = useMemo(() => getOrCreateSessionId(storage), [storage]);
  const [state, dispatch] = useReducer(appReducer, sessionId, createInitialState);
  const socketRef = useRef<SocketClient | null>(null);
  const [showDraftingLive, setShowDraftingLive] = useState(false);

  useEffect(() => {
    const client = clientFactory({
      baseUrl: WS_BASE_URL,
      sessionId,
      callbacks: {
        onConnecting() {
          dispatch({ type: "socket_connecting" });
        },
        onOpen() {
          dispatch({ type: "socket_open" });
        },
        onClose() {
          dispatch({ type: "socket_closed" });
        },
        onError(message) {
          dispatch({ type: "socket_error", message });
        },
        onEvent(event: BaseEventEnvelope) {
          dispatch({
            type: "event_received",
            event,
            receivedAt: new Date().toISOString(),
          });
        },
      },
    });

    socketRef.current = client;
    client.connect();

    return () => {
      client.disconnect();
      socketRef.current = null;
    };
  }, [clientFactory, sessionId]);

  const composerDisabled = state.connectionState !== "connected" || state.runState.status === "running";
  const canCancel = state.runState.status === "running";
  const canApproveOutline = state.pendingAction === "outline_feedback" && !composerDisabled;

  function sendUserMessage(text: string) {
    dispatch({ type: "user_message_sent", text });
    socketRef.current?.send({
      type: "user_message",
      text,
    });
  }

  function approveOutline() {
    setShowDraftingLive(true);
    sendUserMessage("Approve this outline and continue to the draft.");
  }

  function cancelRun() {
    socketRef.current?.send({ type: "cancel_run" });
  }

  const draftState = [...state.conversation].reverse().find((item) => item.kind === "artifact" && item.artifactKind === "draft");
  const draftIsFinal = Boolean(
    draftState && draftState.kind === "artifact" && draftState.artifactKind === "draft" && !draftState.streaming,
  );

  useEffect(() => {
    if (draftIsFinal) {
      setShowDraftingLive(false);
      return;
    }

    if (state.runState.status !== "running" && state.pendingAction !== "draft_feedback") {
      setShowDraftingLive(false);
    }
  }, [draftIsFinal, state.pendingAction, state.runState.status]);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand-block">
          <p className="brand-label">Blog Writer</p>
          <h1>Olostep</h1>
        </div>

        <div className="header-status" aria-label="Assistant status">
          <div className="status-chip">
            <span className="status-chip-label">Connection</span>
            <strong className={`connection connection-${state.connectionState}`}>{state.connectionState}</strong>
          </div>
          <div className="status-chip">
            <span className="status-chip-label">Phase</span>
            <PhaseBadge phase={state.runState.phase} />
          </div>
        </div>
      </header>

      <main className="chat-frame">
        <div className="thread-status" role="status" aria-live="polite">
          {state.statusLine}
        </div>

        <ConversationPanel
          conversation={state.conversation}
          canApproveOutline={canApproveOutline}
          onApproveOutline={approveOutline}
          showDraftingLive={showDraftingLive}
        />

        <ChatComposer
          disabled={composerDisabled}
          onSend={sendUserMessage}
          onCancel={cancelRun}
          canCancel={canCancel}
        />
      </main>
    </div>
  );
}

function getOrCreateSessionId(storage: Storage): string {
  const existing = storage.getItem(SESSION_STORAGE_KEY);
  if (existing) {
    return existing;
  }
  const next = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `session-${Math.random().toString(36).slice(2, 10)}`;
  storage.setItem(SESSION_STORAGE_KEY, next);
  return next;
}
